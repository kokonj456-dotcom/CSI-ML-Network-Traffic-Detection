#!/usr/bin/env python3
"""Autoencoder Experiment for Common Harmonized Multi-Dataset Network Intrusion Detection.

Trains on unified cross-dataset flow features combining NSL-KDD, UNSW-NB15, CIC-IDS2017, and BoT-IoT.
Evaluates across:
  1. Overall Common Test Benchmark (144,876 rows)
  2. KDDTest Subset (22,544 rows)
  3. UNSW-NB15 Test Subset (82,332 rows)
  4. CIC-IDS2017 Test Subset (20,000 rows)
  5. BoT-IoT Test Subset (20,000 rows)
Saves checkpoints and evaluation metrics to model/autoencoder/backup/ for tracking and dashboard integration.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
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
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CENTRAL_DIR = PROJECT_ROOT / "data-pipeline" / "CENTRAL" / "output" / "splits"
BACKUP_DIR = Path(__file__).resolve().parent / "backup"

from model.autoencoder.autoencoder_model import Autoencoder

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


def load_split_encoded(split_name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    split_dir = CENTRAL_DIR / split_name
    feat_df = pd.read_csv(split_dir / "features_encoded_19.csv", low_memory=False)
    lbl_df = pd.read_csv(split_dir / "labels.csv", low_memory=False)
    meta_df = pd.read_csv(split_dir / "metadata.csv", low_memory=False)
    return feat_df, lbl_df, meta_df


def compute_errors(model: Autoencoder, X_scaled: np.ndarray, batch_size: int = 1024, device: torch.device = torch.device("cpu")) -> np.ndarray:
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


def run_common_training(
    epochs: int = 20,
    batch_size: int = 512,
    lr: float = 0.001,
    threshold_percentile: float = 95.0,
    seed: int = 42,
    device_str: str = "auto",
) -> Path:
    start_time = time.time()
    torch.manual_seed(seed)
    np.random.seed(seed)

    device = torch.device("cuda" if device_str == "auto" and torch.cuda.is_available() else "cpu")
    print(f"Running Autoencoder Common Training on {device} (Seed: {seed})...")

    # 1. Load train and validation
    train_feat, train_lbl, _ = load_split_encoded("train")
    val_feat, val_lbl, _ = load_split_encoded("validation")

    feature_cols = [c for c in CORE_FEATURE_COLUMNS if c in train_feat.columns]

    # Filter normal for unsupervised training
    X_train_norm = train_feat.loc[train_lbl["label_binary"].eq(0), feature_cols].values.astype(float)
    X_val_norm = val_feat.loc[val_lbl["label_binary"].eq(0), feature_cols].values.astype(float)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_norm)
    X_val_scaled = scaler.transform(X_val_norm)

    model = Autoencoder(input_dim=len(feature_cols)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = torch.nn.MSELoss()

    train_tensor = torch.tensor(X_train_scaled, dtype=torch.float32)
    train_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(train_tensor),
        batch_size=batch_size,
        shuffle=True,
    )

    best_val_loss = float("inf")
    best_weights = None
    for epoch in range(1, epochs + 1):
        model.train()
        for (batch,) in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            loss = criterion(model(batch), batch)
            loss.backward()
            optimizer.step()

        # Val loss
        val_errors = compute_errors(model, X_val_scaled, device=device)
        v_loss = float(np.mean(val_errors))
        if v_loss < best_val_loss:
            best_val_loss = v_loss
            import copy
            best_weights = copy.deepcopy(model.state_dict())

    if best_weights:
        model.load_state_dict(best_weights)

    # 2. Calibrate threshold
    val_errors = compute_errors(model, X_val_scaled, device=device)
    threshold = float(np.percentile(val_errors, threshold_percentile))

    # 3. Evaluate on Common Test Benchmark
    test_feat, test_lbl, test_meta = load_split_encoded("test")
    X_test_scaled = scaler.transform(test_feat[feature_cols].values.astype(float))
    test_errors = compute_errors(model, X_test_scaled, device=device)
    y_test = test_lbl["label_binary"].values.astype(int)
    y_pred = (test_errors > threshold).astype(int)

    datasets = test_meta["source_dataset"].values
    sub_metrics = {}
    for ds in ["NSL-KDD", "UNSW-NB15", "CIC-IDS2017", "BoT-IoT"]:
        mask = datasets == ds
        if mask.any():
            y_d, p_d = y_test[mask], y_pred[mask]
            cm = confusion_matrix(y_d, p_d, labels=[0, 1])
            tn, fp, fn, tp = cm.ravel()
            sub_metrics[ds] = {
                "accuracy": float(accuracy_score(y_d, p_d)),
                "precision": float(precision_score(y_d, p_d, zero_division=0)),
                "recall": float(recall_score(y_d, p_d, zero_division=0)),
                "f1": float(f1_score(y_d, p_d, zero_division=0)),
                "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else 0.0,
                "confusion_matrix": cm.tolist(),
            }

    cm_all = confusion_matrix(y_test, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm_all.ravel()
    common_metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else 0.0,
        "confusion_matrix": cm_all.tolist(),
    }

    # 4. Save to backup run folder
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    run_id = f"autoencoder-common-binary-{ts}"
    run_dir = BACKUP_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    metrics_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": "Autoencoder (COMMON Binary)",
        "family": "Autoencoder",
        "run_id": run_id,
        "mode": "binary",
        "dataset": "common",
        "threshold": threshold,
        "threshold_percentile": threshold_percentile,
        "hyperparameters": {
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": lr,
            "seed": seed,
            "input_dim": len(feature_cols),
        },
        "common_test_metrics": common_metrics,
        "dataset_metrics": sub_metrics,
        "elapsed_seconds": round(time.time() - start_time, 2),
    }

    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_record, f, indent=2)

    torch.save(model.state_dict(), run_dir / "autoencoder.pth")
    joblib.dump(scaler, run_dir / "scaler.pkl")
    (run_dir / "feature_columns.txt").write_text("\n".join(feature_cols), encoding="utf-8")

    # Also update model root artifacts
    model_root = Path(__file__).resolve().parent
    torch.save(model.state_dict(), model_root / "autoencoder.pth")
    joblib.dump(scaler, model_root / "scaler.pkl")
    (model_root / "feature_columns.txt").write_text("\n".join(feature_cols), encoding="utf-8")

    print(f"\nTraining completed in {metrics_record['elapsed_seconds']}s")
    print(f"Global Accuracy: {common_metrics['accuracy']*100:.2f}% | Recall: {common_metrics['recall']*100:.2f}% | F1: {common_metrics['f1']*100:.2f}%")
    print(f"Run saved to: {run_dir}")

    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Autoencoder on Common Harmonized Dataset")
    parser.add_argument("--epochs", type=int, default=20, help="Epochs (default: 20)")
    parser.add_argument("--batch-size", type=int, default=512, help="Batch size (default: 512)")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate (default: 0.001)")
    parser.add_argument("--seed", type=int, default=42, help="Seed (default: 42)")
    parser.add_argument("--device", type=str, default="auto", help="Device (default: auto)")
    args = parser.parse_args()

    run_common_training(
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        seed=args.seed,
        device_str=args.device,
    )


if __name__ == "__main__":
    main()
