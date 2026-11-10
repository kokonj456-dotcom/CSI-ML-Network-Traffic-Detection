#!/usr/bin/env python3
"""Evaluation Script for Autoencoder on Quad-Dataset Harmonized Benchmark.

Evaluates trained Autoencoder anomaly detector across:
  1. Global Test Benchmark (144,876 flows)
  2. Individual Sub-Datasets (NSL-KDD, UNSW-NB15, CIC-IDS2017, BoT-IoT)
  3. MITRE ATT&CK 6-Class Threat Categories
  4. Cross-Domain Novel & Unseen Attack Generalization (with --unseen)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

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


def load_split_data(split_name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load features, labels, and metadata for a given split."""
    split_dir = SPLITS_DIR / split_name
    feat_path = split_dir / "features_encoded_19.csv"
    lbl_path = split_dir / "labels.csv"
    meta_path = split_dir / "metadata.csv"

    if not feat_path.is_file():
        raise FileNotFoundError(f"Missing {feat_path}. Run data pipeline first.")

    features_df = pd.read_csv(feat_path, low_memory=False)
    labels_df = pd.read_csv(lbl_path, low_memory=False)
    metadata_df = pd.read_csv(meta_path, low_memory=False)

    return features_df, labels_df, metadata_df


def compute_reconstruction_errors(
    model: Autoencoder,
    X_scaled: np.ndarray,
    batch_size: int = 1024,
    device: torch.device = torch.device("cpu"),
) -> np.ndarray:
    """Compute MSE reconstruction error per flow."""
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ประเมินโมเดล Autoencoder บนชุดทดสอบ Quad-Dataset Harmonized"
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test",
        choices=["test", "validation", "train"],
        help="ชุด Split ที่ต้องการประเมิน (default: test)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="all",
        choices=["all", "NSL-KDD", "UNSW-NB15", "CIC-IDS2017", "BoT-IoT"],
        help="เลือกชุดข้อมูลย่อยที่ต้องการประเมิน หรือ 'all' สำหรับทั้งหมด (default: all)",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        default=95.0,
        help="เปอร์เซ็นไทล์สำหรับกำหนด Threshold จาก Validation (default: 95.0)",
    )
    parser.add_argument(
        "--unseen",
        action="store_true",
        help="แสดงตารางวิเคราะห์การตรวจจับการโจมตีข้ามชุดข้อมูลและประเภท Novel Attacks",
    )
    parser.add_argument("--device", type=str, default="auto", help="อุปกรณ์ (auto, cuda, cpu)")
    args = parser.parse_args()

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    # 1. โหลดโมเดล, Scaler และ Feature List
    model_path = MODEL_DIR / "autoencoder.pth"
    scaler_path = MODEL_DIR / "scaler.pkl"
    features_path = MODEL_DIR / "feature_columns.txt"

    if not model_path.is_file():
        raise FileNotFoundError(f"Missing {model_path}. Please train the model first.")

    feature_columns = features_path.read_text(encoding="utf-8").strip().splitlines()
    scaler = joblib.load(scaler_path)

    model = Autoencoder(input_dim=len(feature_columns)).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model.eval()

    print(f"Loaded Autoencoder model from {model_path} (Input Dim: {len(feature_columns)})")

    # 2. คำนวณ Threshold จาก Normal Validation Set
    val_feat, val_lbl, _ = load_split_data("validation")
    normal_val_mask = val_lbl["label_binary"].eq(0)
    X_val_normal = val_feat.loc[normal_val_mask, feature_columns].values.astype(float)
    X_val_scaled = scaler.transform(X_val_normal)

    val_errors = compute_reconstruction_errors(model, X_val_scaled, device=device)
    threshold = float(np.percentile(val_errors, args.percentile))
    print(f"Calculated Alert Threshold (Percentile {args.percentile}%): {threshold:.6f}")

    # 3. โหลดชุดข้อมูลที่จะประเมิน
    eval_feat, eval_lbl, eval_meta = load_split_data(args.split)

    if args.dataset != "all":
        mask = eval_meta["source_dataset"] == args.dataset
        eval_feat = eval_feat[mask].reset_index(drop=True)
        eval_lbl = eval_lbl[mask].reset_index(drop=True)
        eval_meta = eval_meta[mask].reset_index(drop=True)
        print(f"Filtered for dataset: {args.dataset} ({len(eval_feat):,} flows)")

    X_eval = eval_feat[feature_columns].values.astype(float)
    y_true = eval_lbl["label_binary"].values.astype(int)
    attack_cat_id = eval_lbl["attack_category_id"].values.astype(int)

    X_eval_scaled = scaler.transform(X_eval)
    test_errors = compute_reconstruction_errors(model, X_eval_scaled, device=device)
    y_pred = (test_errors > threshold).astype(int)

    # 4. คำนวณ Metrics
    acc = float(accuracy_score(y_true, y_pred))
    prec = float(precision_score(y_true, y_pred, zero_division=0))
    rec = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    fpr = float(fp / (fp + tn)) if (fp + tn) else 0.0

    print("\n" + "=" * 80)
    print(f"EVALUATION SUMMARY [{args.split.upper()} - {args.dataset}] (Total Flows: {len(y_true):,})")
    print("=" * 80)
    print(f"Accuracy:                 {acc * 100:.2f}%")
    print(f"Precision:                {prec * 100:.2f}%")
    print(f"Recall (Detection Rate):  {rec * 100:.2f}%")
    print(f"F1-Score:                 {f1 * 100:.2f}%")
    print(f"False Positive Rate:      {fpr * 100:.2f}%")
    print(f"Confusion Matrix:         TN={tn:,}, FP={fp:,}, FN={fn:,}, TP={tp:,}")

    # Breakdown by Attack Category
    print("\n" + "-" * 80)
    print("ATTACK CATEGORY DETECTION RATES:")
    print(f"{'Category':<32} | {'Flows':>10} | {'Detection Rate (%)':>20}")
    print("-" * 80)
    for cid in range(6):
        c_mask = attack_cat_id == cid
        total_c = int(c_mask.sum())
        if total_c == 0:
            continue
        flagged = int((y_pred[c_mask] == 1).sum())
        rate = float(flagged / total_c)
        print(f"Class {cid}: {CLASS_NAMES[cid]:<23} | {total_c:>10,} | {rate * 100:>19.2f}%")
    print("-" * 80)

    # 5. Cross-domain / Unseen analysis if requested
    if args.unseen:
        is_anomaly = test_errors > threshold
        results = []
        for (dataset, cat_id), group_idx in eval_lbl.groupby([eval_meta["source_dataset"], "attack_category_id"]).groups.items():
            total = len(group_idx)
            detected = int(is_anomaly[group_idx].sum())
            rate = detected / total if total else 0.0
            results.append({
                "source_dataset": dataset,
                "attack_category_id": int(cat_id),
                "attack_category": CLASS_NAMES[int(cat_id)],
                "total_flows": total,
                "detected_flows": detected,
                "detection_rate": round(rate, 4),
                "mean_reconstruction_error": round(float(test_errors[group_idx].mean()), 6),
            })

        res_df = pd.DataFrame(results).sort_values(["source_dataset", "attack_category_id"])
        print("\n" + "=" * 90)
        print("CROSS-DOMAIN ATTACK GENERALIZATION & DETECTION REPORT")
        print("=" * 90)
        print(res_df.to_string(index=False))


if __name__ == "__main__":
    main()
