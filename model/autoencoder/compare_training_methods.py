#!/usr/bin/env python3
"""Comparison of 4 Training Strategies for Autoencoder Anomaly Detection.

Replicates the 4-Method Imbalance & Resampling Ablation Study:
  1. ไม่ทำ SMOTE ไม่เพิ่ม weight (Baseline: Train split, unweighted)
  2. ไม่ทำ SMOTE + weight R2L (Train split, sample-weighted R2L)
  3. ทำ SMOTENC (Train SMOTE split, unweighted)
  4. ทำ SMOTENC + weight R2L (Train SMOTE split, sample-weighted R2L)

Generates comparison tables matching the benchmark schema:
  - วิธีฝึก (Training Method)
  - Accuracy
  - Precision
  - Recall
  - F1-score
  - (Bonus: R2L Detection Rate & False Positive Rate)
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

# Ensure stdout uses UTF-8 to prevent Thai garbled characters on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.autoencoder.autoencoder_model import Autoencoder

CENTRAL_DIR = PROJECT_ROOT / "data-pipeline" / "CENTRAL"
SPLITS_DIR = CENTRAL_DIR / "output" / "splits"
MODEL_DIR = PROJECT_ROOT / "model" / "autoencoder"

CORE_FEATURE_COLUMNS = [
    "log_duration",
    "log_bytes_forward",
    "log_bytes_backward",
    "signed_log_bytes_ratio",
    "proto_tcp",
    "proto_udp",
    "proto_icmp",
    "proto_other",
    "service_dns",
    "service_ftp",
    "service_http",
    "service_https_ssl",
    "service_smtp",
    "service_ssh",
    "service_other",
    "state_established",
    "state_no-reply",
    "state_reset",
    "state_other",
]


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_split_tables(split_name: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    split_dir = SPLITS_DIR / split_name
    feat_path = split_dir / "features_encoded_19.csv"
    lbl_path = split_dir / "labels.csv"
    meta_path = split_dir / "metadata.csv"

    if not feat_path.is_file():
        raise FileNotFoundError(f"Missing {feat_path}")

    features_df = pd.read_csv(feat_path, low_memory=False)[CORE_FEATURE_COLUMNS]
    labels_df = pd.read_csv(lbl_path, low_memory=False)
    metadata_df = pd.read_csv(meta_path, low_memory=False)

    return features_df, labels_df, metadata_df


def train_regularized_autoencoder(
    X_norm_scaled: np.ndarray,
    X_r2l_scaled: np.ndarray,
    X_val_norm_scaled: np.ndarray,
    r2l_weight: float = 1.0,
    epochs: int = 8,
    batch_size: int = 512,
    lr: float = 0.001,
    margin_lambda: float = 0.05,
    margin: float = 1.2,
    device: torch.device = torch.device("cpu"),
) -> Autoencoder:
    """Train Autoencoder on normal flows with contrastive margin penalty on R2L attacks."""
    input_dim = X_norm_scaled.shape[1]
    model = Autoencoder(input_dim=input_dim, hidden_dims=(14, 8)).to(device)
    criterion_mse = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    train_norm_tensor = torch.tensor(X_norm_scaled, dtype=torch.float32)
    val_norm_tensor = torch.tensor(X_val_norm_scaled, dtype=torch.float32).to(device)

    # R2L attack samples for contrastive regularization
    has_r2l = len(X_r2l_scaled) > 0
    if has_r2l:
        r2l_tensor = torch.tensor(X_r2l_scaled, dtype=torch.float32)
        r2l_loader = DataLoader(
            TensorDataset(r2l_tensor),
            batch_size=min(batch_size // 4, max(32, len(X_r2l_scaled))),
            shuffle=True,
            drop_last=False,
        )
        r2l_iter = iter(r2l_loader)

    train_loader = DataLoader(
        TensorDataset(train_norm_tensor),
        batch_size=batch_size,
        shuffle=True,
    )

    best_val_loss = float("inf")
    best_weights = None

    for epoch in range(1, epochs + 1):
        model.train()
        for (batch_norm,) in train_loader:
            batch_norm = batch_norm.to(device)
            optimizer.zero_grad()

            # Normal reconstruction loss (minimize error)
            recon_norm = model(batch_norm)
            loss_norm = criterion_mse(recon_norm, batch_norm)

            loss = loss_norm

            # Contrastive margin loss on R2L attacks (push reconstruction error >= margin)
            if has_r2l and r2l_weight > 0.0:
                try:
                    (batch_r2l,) = next(r2l_iter)
                except StopIteration:
                    r2l_iter = iter(r2l_loader)
                    (batch_r2l,) = next(r2l_iter)

                batch_r2l = batch_r2l.to(device)
                recon_r2l = model(batch_r2l)
                recon_r2l_err = torch.mean((batch_r2l - recon_r2l) ** 2, dim=1)
                
                # Margin loss: max(0, margin - error)
                loss_margin = torch.mean(torch.relu(margin - recon_r2l_err))
                loss = loss + (margin_lambda * r2l_weight) * loss_margin

            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_recon = model(val_norm_tensor)
            val_loss = criterion_mse(val_recon, val_norm_tensor).item()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = copy.deepcopy(model.state_dict())

    if best_weights is not None:
        model.load_state_dict(best_weights)
    model.eval()
    return model


def compute_reconstruction_error(
    model: Autoencoder,
    X_scaled: np.ndarray,
    device: torch.device,
    batch_size: int = 2048,
) -> np.ndarray:
    model.eval()
    errors: List[np.ndarray] = []
    num_samples = len(X_scaled)

    with torch.no_grad():
        for start_idx in range(0, num_samples, batch_size):
            end_idx = min(start_idx + batch_size, num_samples)
            batch = torch.tensor(X_scaled[start_idx:end_idx], dtype=torch.float32).to(device)
            recon = model(batch)
            batch_err = torch.mean((batch - recon) ** 2, dim=1).cpu().numpy()
            errors.append(batch_err)

    return np.concatenate(errors, axis=0)


def calibrate_threshold(
    val_errors: np.ndarray,
    val_y_binary: np.ndarray,
    val_y_cat: np.ndarray,
    r2l_weight: float = 1.0,
    search_percentiles: np.ndarray = None,
) -> Tuple[float, float]:
    """Find the optimal threshold on validation set considering R2L sample weights."""
    norm_mask = val_y_binary == 0
    val_norm_errors = val_errors[norm_mask]

    if search_percentiles is None:
        search_percentiles = np.linspace(80.0, 98.0, 37)

    # Sample weights: R2L attacks (cat 4) get weight = r2l_weight
    sample_weights = np.ones(len(val_y_binary), dtype=np.float32)
    if r2l_weight > 1.0:
        sample_weights[val_y_cat == 4] = r2l_weight

    best_score = -1.0
    best_threshold = float(np.percentile(val_norm_errors, 95.0))
    best_pct = 95.0

    for pct in search_percentiles:
        tau = float(np.percentile(val_norm_errors, pct))
        preds = (val_errors >= tau).astype(int)

        # Weighted F1 optimization on validation
        f1 = f1_score(val_y_binary, preds, sample_weight=sample_weights, zero_division=0)

        if f1 > best_score:
            best_score = f1
            best_threshold = tau
            best_pct = round(pct, 2)

    return best_threshold, best_pct


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_cat: np.ndarray,
) -> Dict[str, float]:
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    # R2L Detection Rate specifically
    r2l_mask = y_cat == 4
    if np.any(r2l_mask):
        r2l_rec = float(np.mean(y_pred[r2l_mask] == 1))
    else:
        r2l_rec = 0.0

    return {
        "accuracy": acc * 100.0,
        "precision": prec * 100.0,
        "recall": rec * 100.0,
        "f1": f1 * 100.0,
        "fpr": fpr * 100.0,
        "r2l_recall": r2l_rec * 100.0,
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


def run_comparative_experiment(
    epochs: int = 8,
    batch_size: int = 512,
    lr: float = 0.001,
    r2l_weight: float = 5.0,
    seed: int = 42,
    device_str: str = "auto",
) -> pd.DataFrame:
    if device_str == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(device_str)

    set_seed(seed)
    print("=" * 80)
    print(f"RUNNING 4-METHOD ABLATION EXPERIMENT FOR AUTOENCODER (Device: {device})")
    print("=" * 80)

    # 1. Load Validation & Test Splits
    print("\n[1/3] Loading Test and Validation Splits...")
    X_test_df, y_test_df, _ = load_split_tables("test")
    X_val_df, y_val_df, _ = load_split_tables("validation")

    y_test_bin = y_test_df["label_binary"].values
    y_test_cat = y_test_df["attack_category_id"].values

    y_val_bin = y_val_df["label_binary"].values
    y_val_cat = y_val_df["attack_category_id"].values

    # 2. Fit StandardScaler on Baseline Train Split (Normal only)
    print("[2/3] Loading Train Baseline and Fitting Scaler...")
    X_train_df, y_train_df, _ = load_split_tables("train")
    norm_mask_train = y_train_df["label_binary"].eq(0).values
    r2l_mask_train = y_train_df["attack_category_id"].eq(4).values

    scaler = StandardScaler()
    scaler.fit(X_train_df.loc[norm_mask_train].values)

    X_train_norm_scaled = scaler.transform(X_train_df.loc[norm_mask_train].values)
    X_train_r2l_scaled = scaler.transform(X_train_df.loc[r2l_mask_train].values)

    X_val_scaled = scaler.transform(X_val_df.values)
    X_test_scaled = scaler.transform(X_test_df.values)

    norm_mask_val = y_val_bin == 0
    X_val_norm_scaled = X_val_scaled[norm_mask_val]

    # Load Train SMOTE Split
    print("      Loading Train SMOTENC Split...")
    X_smote_df, y_smote_df, _ = load_split_tables("train_smote")
    r2l_mask_smote = y_smote_df["attack_category_id"].eq(4).values
    X_smote_r2l_scaled = scaler.transform(X_smote_df.loc[r2l_mask_smote].values)

    # Define the 4 Strategies
    strategies = [
        {
            "name": "ไม่ทำ SMOTE ไม่เพิ่ม weight",
            "smote": False,
            "weight_r2l": False,
            "r2l_mult": 1.0,
            "r2l_scaled": X_train_r2l_scaled,
            "reg_weight": 0.0,
        },
        {
            "name": "ไม่ทำ SMOTE + weight R2L",
            "smote": False,
            "weight_r2l": True,
            "r2l_mult": r2l_weight,
            "r2l_scaled": X_train_r2l_scaled,
            "reg_weight": r2l_weight,
        },
        {
            "name": "ทำ SMOTENC",
            "smote": True,
            "weight_r2l": False,
            "r2l_mult": 1.0,
            "r2l_scaled": X_smote_r2l_scaled,
            "reg_weight": 1.0,
        },
        {
            "name": "ทำ SMOTENC + weight R2L",
            "smote": True,
            "weight_r2l": True,
            "r2l_mult": r2l_weight,
            "r2l_scaled": X_smote_r2l_scaled,
            "reg_weight": r2l_weight,
        },
    ]

    print(f"      Baseline R2L samples: {len(X_train_r2l_scaled):,} | SMOTENC R2L samples: {len(X_smote_r2l_scaled):,}")
    print("\n[3/3] Training and Evaluating 4 Strategies...")
    results_list: List[Dict[str, Any]] = []

    for i, strat in enumerate(strategies, 1):
        print(f"\n---> [{i}/4] กำลังประเมิน: {strat['name']}")
        t0 = time.time()

        model = train_regularized_autoencoder(
            X_norm_scaled=X_train_norm_scaled,
            X_r2l_scaled=strat["r2l_scaled"],
            X_val_norm_scaled=X_val_norm_scaled,
            r2l_weight=strat["reg_weight"],
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            device=device,
        )

        # Validation Reconstruction Errors
        val_errors = compute_reconstruction_error(model, X_val_scaled, device=device)

        # Calibrate Threshold with / without R2L Weight
        mult = strat["r2l_mult"]
        threshold, pct = calibrate_threshold(
            val_errors=val_errors,
            val_y_binary=y_val_bin,
            val_y_cat=y_val_cat,
            r2l_weight=mult,
        )

        # Evaluate on Test Set
        test_errors = compute_reconstruction_error(model, X_test_scaled, device=device)
        test_preds = (test_errors >= threshold).astype(int)

        metrics = evaluate_predictions(y_test_bin, test_preds, y_test_cat)
        elapsed = round(time.time() - t0, 2)

        results_list.append({
            "วิธีฝึก": strat["name"],
            "Accuracy": f"{metrics['accuracy']:.2f}%",
            "Precision": f"{metrics['precision']:.2f}%",
            "Recall": f"{metrics['recall']:.2f}%",
            "F1-score": f"{metrics['f1']:.2f}%",
            "R2L Recall": f"{metrics['r2l_recall']:.2f}%",
            "FPR": f"{metrics['fpr']:.2f}%",
            "Threshold": round(threshold, 6),
            "Percentile": pct,
            "Elapsed (s)": elapsed,
            "_raw": metrics,
        })
        print(f"     Accuracy: {metrics['accuracy']:.2f}% | Precision: {metrics['precision']:.2f}% | Recall: {metrics['recall']:.2f}% | F1: {metrics['f1']:.2f}% | R2L Recall: {metrics['r2l_recall']:.2f}%")

    results_df = pd.DataFrame(results_list)

    # Print Clean Display Table
    print("\n" + "=" * 80)
    print("สรุปผลการทดลองเปรียบเทียบวิธีฝึกโมเดล (Ablation Comparison Table):")
    print("=" * 80)
    display_cols = ["วิธีฝึก", "Accuracy", "Precision", "Recall", "F1-score"]
    print(results_df[display_cols].to_string(index=False))
    print("=" * 80)

    # Save to JSON and Markdown
    save_path_json = MODEL_DIR / "comparison_results.json"
    with open(save_path_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "test_flows": len(X_test_df),
                "epochs": epochs,
                "r2l_weight": r2l_weight,
                "results": results_list,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    save_path_md = MODEL_DIR / "COMPARISON_TABLE.md"
    md_content = f"""# ตารางเปรียบเทียบผลการฝึกโมเดล Autoencoder

การทดลองเปรียบเทียบกลยุทธ์การจัดการ Imbalance (SMOTENC & Sample Weighting) บนชุดทดสอบกลาง Quad-Dataset (144,876 flows)

| วิธีฝึก | Accuracy | Precision | Recall | F1-score |
| :--- | :---: | :---: | :---: | :---: |
"""
    for r in results_list:
        md_content += f"| **{r['วิธีฝึก']}** | {r['Accuracy']} | {r['Precision']} | {r['Recall']} | {r['F1-score']} |\n"

    md_content += f"""
### รายละเอียดเพิ่มเติมเชิงลึก (Detailed Metrics Breakdown)
| วิธีฝึก | R2L Detection Rate (Recall) | False Positive Rate (FPR) | Alert Threshold |
| :--- | :---: | :---: | :---: |
"""
    for r in results_list:
        md_content += f"| **{r['วิธีฝึก']}** | {r['R2L Recall']} | {r['FPR']} | {r['Threshold']} ({r['Percentile']}%) |\n"

    save_path_md.write_text(md_content, encoding="utf-8")
    print(f"\nบันทึกผลการทดลองเปรียบเทียบแล้วที่:")
    print(f"  - {save_path_json}")
    print(f"  - {save_path_md}\n")

    return results_df


def main():
    parser = argparse.ArgumentParser(description="เปรียบเทียบ 4 วิธีฝึกสำหรับ Autoencoder")
    parser.add_argument("--epochs", type=int, default=8, help="จำนวนรอบในการฝึกแต่ละโมเดล (default: 8)")
    parser.add_argument("--batch-size", type=int, default=512, help="Batch size (default: 512)")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate (default: 0.001)")
    parser.add_argument("--r2l-weight", type=float, default=5.0, help="ตัวคูณน้ำหนักสำหรับ R2L (default: 5.0)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--device", type=str, default="auto", help="Device (auto, cpu, cuda)")

    args = parser.parse_args()
    run_comparative_experiment(
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        r2l_weight=args.r2l_weight,
        seed=args.seed,
        device_str=args.device,
    )


if __name__ == "__main__":
    main()
