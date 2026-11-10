#!/usr/bin/env python3
"""Autoencoder Anomaly Detection for Quad-Domain Harmonized Dataset.

Supports:
  - 4-Dataset Unified Benchmark (NSL-KDD, UNSW-NB15, CIC-IDS2017, BoT-IoT)
  - 19 Core Joint Flow Features
  - Unsupervised Training on Benign/Normal Network Traffic (label_binary == 0)
  - Dynamic Validation-based Threshold Calibration (Percentile-based)
  - Experiment Logging into backup/
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.autoencoder.autoencoder_model import Autoencoder

CENTRAL_DIR = PROJECT_ROOT / "data-pipeline" / "CENTRAL"
SPLITS_DIR = CENTRAL_DIR / "output" / "splits"
MODEL_DIR = PROJECT_ROOT / "model" / "autoencoder"
BACKUP_DIR = MODEL_DIR / "backup"

CLASS_NAMES = [
    "Benign / Normal",
    "Denial of Service (DoS)",
    "Reconnaissance & Probing",
    "Exploits & PrivEsc",
    "Credential Abuse (R2L)",
    "Malware, C2 & Botnet",
]

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
    """Set random seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_split_data(split_name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load 19-dimensional features, labels, and metadata for a given split."""
    split_dir = SPLITS_DIR / split_name
    feat_path = split_dir / "features_encoded_19.csv"
    lbl_path = split_dir / "labels.csv"
    meta_path = split_dir / "metadata.csv"

    if not feat_path.is_file():
        raise FileNotFoundError(f"Missing {feat_path}. Run data pipeline first.")
    if not lbl_path.is_file():
        raise FileNotFoundError(f"Missing {lbl_path}.")
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing {meta_path}.")

    features_df = pd.read_csv(feat_path, low_memory=False)
    labels_df = pd.read_csv(lbl_path, low_memory=False)
    metadata_df = pd.read_csv(meta_path, low_memory=False)

    return features_df, labels_df, metadata_df


def train_autoencoder(
    X_train_scaled: np.ndarray,
    X_val_scaled: np.ndarray,
    epochs: int = 25,
    batch_size: int = 256,
    lr: float = 0.001,
    device: torch.device = torch.device("cpu"),
) -> tuple[Autoencoder, list[dict[str, float | int]]]:
    """Train Autoencoder on normal network traffic and retain best weights."""
    input_dim = X_train_scaled.shape[1]
    model = Autoencoder(input_dim=input_dim).to(device)

    train_tensor = torch.tensor(X_train_scaled, dtype=torch.float32)
    val_tensor = torch.tensor(X_val_scaled, dtype=torch.float32).to(device)

    train_dataset = TensorDataset(train_tensor)
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
    )

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    history: list[dict[str, float | int]] = []
    best_val_loss = float("inf")
    best_weights = None
    best_epoch = 1

    print("\n" + "=" * 80)
    print(f"TRAINING AUTOENCODER (Input Dim: {input_dim}, Device: {device}, Epochs: {epochs})")
    print("=" * 80)

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        model.train()
        total_train_loss = 0.0

        for (batch,) in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            reconstructed = model(batch)
            loss = criterion(reconstructed, batch)
            loss.backward()
            optimizer.step()
            total_train_loss += loss.item() * batch.size(0)

        train_loss = total_train_loss / len(train_dataset)

        # Validation Loss
        model.eval()
        total_val_loss = 0.0
        with torch.no_grad():
            for start in range(0, len(val_tensor), batch_size):
                batch_val = val_tensor[start : start + batch_size]
                reconstructed_val = model(batch_val)
                loss_val = criterion(reconstructed_val, batch_val)
                total_val_loss += loss_val.item() * batch_val.size(0)

        val_loss = total_val_loss / len(val_tensor)
        duration = time.time() - t0

        is_best = ""
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = copy.deepcopy(model.state_dict())
            best_epoch = epoch
            is_best = " [BEST]"

        history.append({
            "epoch": epoch,
            "train_loss": round(train_loss, 6),
            "val_loss": round(val_loss, 6),
            "epoch_time_sec": round(duration, 2),
        })

        print(
            f"Epoch [{epoch:02d}/{epochs:02d}] "
            f"Train Loss: {train_loss:.6f} | "
            f"Val Loss: {val_loss:.6f}{is_best} "
            f"({duration:.2f}s)"
        )

    if best_weights is not None:
        model.load_state_dict(best_weights)
        print(f"\nLoaded best model checkpoint from Epoch {best_epoch} (Val Loss: {best_val_loss:.6f})")

    return model, history


def calculate_reconstruction_errors(
    model: Autoencoder,
    X_scaled: np.ndarray,
    batch_size: int = 1024,
    device: torch.device = torch.device("cpu"),
) -> np.ndarray:
    """Compute Mean Squared Error (MSE) per flow."""
    model.eval()
    errors = []
    tensor_data = torch.tensor(X_scaled, dtype=torch.float32)

    with torch.no_grad():
        for start in range(0, len(tensor_data), batch_size):
            batch = tensor_data[start : start + batch_size].to(device)
            reconstructed = model(batch)
            mse = torch.mean((batch - reconstructed) ** 2, dim=1).cpu().numpy()
            errors.append(mse)

    return np.concatenate(errors, axis=0)


def evaluate_quad_test(
    model: Autoencoder,
    scaler: StandardScaler,
    feature_columns: list[str],
    X_val_scaled: np.ndarray,
    threshold_percentile: float = 95.0,
    device: torch.device = torch.device("cpu"),
) -> dict:
    """Evaluate Autoencoder across the Quad Benchmark test set."""
    print("\n" + "=" * 80)
    print("QUAD-DATASET CENTRAL TEST BENCHMARK EVALUATION")
    print("=" * 80)

    val_errors = calculate_reconstruction_errors(model, X_val_scaled, device=device)
    threshold = float(np.percentile(val_errors, threshold_percentile))
    print(f"Validation Calibrated Threshold (Percentile {threshold_percentile}%): {threshold:.6f}")

    test_feat, test_lbl, test_meta = load_split_data("test")
    X_test_raw = test_feat[feature_columns].values.astype(float)
    y_test_binary = test_lbl["label_binary"].values.astype(int)
    attack_cat_id = test_lbl["attack_category_id"].values.astype(int)
    datasets = test_meta["source_dataset"].values

    X_test_scaled = scaler.transform(X_test_raw)
    test_errors = calculate_reconstruction_errors(model, X_test_scaled, device=device)
    y_pred = (test_errors > threshold).astype(int)

    acc = float(accuracy_score(y_test_binary, y_pred))
    prec = float(precision_score(y_test_binary, y_pred, zero_division=0))
    rec = float(recall_score(y_test_binary, y_pred, zero_division=0))
    f1 = float(f1_score(y_test_binary, y_pred, zero_division=0))
    tn, fp, fn, tp = confusion_matrix(y_test_binary, y_pred, labels=[0, 1]).ravel()
    fpr = float(fp / (fp + tn)) if (fp + tn) else 0.0

    print(f"\n[GLOBAL BENCHMARK RESULTS - {len(y_test_binary):,} Flows]")
    print(f"  Accuracy:  {acc * 100:.2f}%")
    print(f"  Precision: {prec * 100:.2f}%")
    print(f"  Recall:    {rec * 100:.2f}% (Attack Detection Rate)")
    print(f"  F1-Score:  {f1 * 100:.2f}%")
    print(f"  FPR:       {fpr * 100:.2f}% (Benign False Positive Rate)")
    print(f"  Confusion: TN={tn:,}, FP={fp:,}, FN={fn:,}, TP={tp:,}")

    dataset_breakdown = {}
    print("\n" + "-" * 80)
    print("SUB-DATASET BENCHMARK PERFORMANCE BREAKDOWN:")
    print(f"{'Dataset':<15} | {'Total Flows':>11} | {'Acc (%)':>7} | {'Recall (%)':>10} | {'FPR (%)':>7} | {'F1 (%)':>7}")
    print("-" * 80)

    for ds in ["NSL-KDD", "UNSW-NB15", "CIC-IDS2017", "BoT-IoT"]:
        mask = datasets == ds
        if not mask.any():
            continue
        y_ds = y_test_binary[mask]
        pred_ds = y_pred[mask]

        ds_acc = float(accuracy_score(y_ds, pred_ds))
        ds_rec = float(recall_score(y_ds, pred_ds, zero_division=0))
        ds_f1 = float(f1_score(y_ds, pred_ds, zero_division=0))
        cm = confusion_matrix(y_ds, pred_ds, labels=[0, 1])
        ds_tn, ds_fp, ds_fn, ds_tp = cm.ravel()
        ds_fpr = float(ds_fp / (ds_fp + ds_tn)) if (ds_fp + ds_tn) else 0.0

        dataset_breakdown[ds] = {
            "total_flows": int(mask.sum()),
            "accuracy": round(ds_acc, 4),
            "recall": round(ds_rec, 4),
            "fpr": round(ds_fpr, 4),
            "f1_score": round(ds_f1, 4),
            "confusion_matrix": [int(ds_tn), int(ds_fp), int(ds_fn), int(ds_tp)],
        }
        print(f"{ds:<15} | {mask.sum():>11,} | {ds_acc * 100:>7.2f} | {ds_rec * 100:>10.2f} | {ds_fpr * 100:>7.2f} | {ds_f1 * 100:>7.2f}")

    category_breakdown = {}
    print("\n" + "-" * 80)
    print("MITRE ATT&CK 6-CLASS TAXONOMY DETECTION RATES:")
    print(f"{'Class ID & Name':<32} | {'Total Flows':>11} | {'Flagged as Anomaly (%)':>22}")
    print("-" * 80)

    for cid in range(6):
        c_mask = attack_cat_id == cid
        total_c = int(c_mask.sum())
        if total_c == 0:
            continue
        flagged = int((y_pred[c_mask] == 1).sum())
        rate = float(flagged / total_c)

        category_breakdown[cid] = {
            "class_name": CLASS_NAMES[cid],
            "total_flows": total_c,
            "flagged_as_anomaly": flagged,
            "detection_rate": round(rate, 4),
        }
        label_text = f"Class {cid}: {CLASS_NAMES[cid]}"
        print(f"{label_text:<32} | {total_c:>11,} | {rate * 100:>21.2f}%")

    print("-" * 80)

    results = {
        "benchmark": "CENTRAL Quad-Dataset Anomaly Detection",
        "threshold": round(threshold, 6),
        "threshold_percentile": threshold_percentile,
        "global_metrics": {
            "total_test_flows": len(y_test_binary),
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "fpr": round(fpr, 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        },
        "dataset_breakdown": dataset_breakdown,
        "category_breakdown": category_breakdown,
    }

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ฝึกและประเมินโมเดล Autoencoder สำหรับตรวจจับ Anomaly บน CENTRAL Quad-Dataset"
    )
    parser.add_argument("--epochs", type=int, default=20, help="จำนวน Epoch ในการฝึก (default: 20)")
    parser.add_argument("--batch-size", type=int, default=512, help="ขนาด Batch size (default: 512)")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning Rate (default: 0.001)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument(
        "--train-split",
        type=str,
        default="train",
        choices=["train", "train_smote", "train_full", "train_full_smote"],
        help="ชุด Split สำหรับฝึกโมเดล (default: train)",
    )
    parser.add_argument(
        "--threshold-percentile",
        type=float,
        default=95.0,
        help="เปอร์เซ็นไทล์จาก Normal Validation Error สำหรับ Threshold (default: 95.0)",
    )
    parser.add_argument("--skip-eval", action="store_true", help="ข้ามขั้นตอนการประเมินผลบน Test set")
    parser.add_argument("--device", type=str, default="auto", help="อุปกรณ์ประมวลผล (auto, cuda, cpu)")

    args = parser.parse_args()

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    set_seed(args.seed)
    print(f"Using device: {device} | Seed: {args.seed} | Train Split: {args.train_split}")

    # 1. โหลดข้อมูล Training
    print(f"\n[1/4] Loading {args.train_split} split...")
    train_feat, train_lbl, train_meta = load_split_data(args.train_split)
    feature_columns = [col for col in CORE_FEATURE_COLUMNS if col in train_feat.columns]

    if len(feature_columns) != 19:
        raise ValueError(f"Expected 19 core features, found {len(feature_columns)}")

    normal_train_mask = train_lbl["label_binary"].eq(0)
    X_train_normal = train_feat.loc[normal_train_mask, feature_columns].values.astype(float)
    print(f"  Total train flows: {len(train_feat):,} | Normal flows for training: {len(X_train_normal):,}")

    # 2. โหลดข้อมูล Validation
    print("\n[2/4] Loading validation split...")
    val_feat, val_lbl, val_meta = load_split_data("validation")
    normal_val_mask = val_lbl["label_binary"].eq(0)
    X_val_normal = val_feat.loc[normal_val_mask, feature_columns].values.astype(float)
    print(f"  Total val flows: {len(val_feat):,} | Normal flows for validation: {len(X_val_normal):,}")

    # 3. ปรับสเกลข้อมูล
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_normal)
    X_val_scaled = scaler.transform(X_val_normal)

    # 4. ฝึกโมเดล
    print("\n[3/4] Training Autoencoder model...")
    t_start = time.time()
    model, history = train_autoencoder(
        X_train_scaled=X_train_scaled,
        X_val_scaled=X_val_scaled,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        device=device,
    )
    elapsed = round(time.time() - t_start, 2)

    # 5. ประเมินผล
    eval_results = None
    if not args.skip_eval:
        print("\n[4/4] Evaluating model...")
        eval_results = evaluate_quad_test(
            model=model,
            scaler=scaler,
            feature_columns=feature_columns,
            X_val_scaled=X_val_scaled,
            threshold_percentile=args.threshold_percentile,
            device=device,
        )

    # 6. บันทึก Artifacts เข้า backup/ run folder
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"autoencoder-common-binary-{ts}"
    run_dir = BACKUP_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # บันทึกไฟล์ใน run folder
    torch.save(model.state_dict(), run_dir / "autoencoder.pth")
    joblib.dump(scaler, run_dir / "scaler.pkl")
    (run_dir / "feature_columns.txt").write_text("\n".join(feature_columns), encoding="utf-8")
    pd.DataFrame(history).to_csv(run_dir / "training_history.csv", index=False)

    run_meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": "Autoencoder Anomaly Detector",
        "family": "Autoencoder",
        "run_id": run_id,
        "mode": "binary",
        "dataset": "CENTRAL Quad-Dataset",
        "hyperparameters": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "seed": args.seed,
            "input_dim": len(feature_columns),
            "hidden_dims": list(model.hidden_dims),
        },
        "elapsed_seconds": elapsed,
        "evaluation": eval_results,
    }
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(run_meta, f, indent=2, ensure_ascii=False)

    # สำเนาไฟล์หลักมาที่ root ของ model/autoencoder
    torch.save(model.state_dict(), MODEL_DIR / "autoencoder.pth")
    joblib.dump(scaler, MODEL_DIR / "scaler.pkl")
    (MODEL_DIR / "feature_columns.txt").write_text("\n".join(feature_columns), encoding="utf-8")

    print(f"\nModel checkpoint and metrics saved to: {run_dir}")


if __name__ == "__main__":
    main()
