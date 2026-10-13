"""
Unified Multi-Model Training Service
Supports live on-demand training with configurable hyperparameters,
real-time progress tracking, and Apple Silicon MPS/GPU acceleration across:
  1. XGBoost (Gradient Boosted Decision Trees)
  2. MLP (Deep Multi-Layer Perceptron)
  3. Autoencoder (Unsupervised Reconstruction Anomaly Detector)
  4. Isolation Forest (Unsupervised Quantile Anomaly Detector)
"""

from __future__ import annotations

# Import torch before third-party native libraries (xgboost, sklearn) to avoid OpenMP symbol collision on macOS
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier
import xgboost as xgb
from sklearn.ensemble import IsolationForest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PIPELINE = PROJECT_ROOT / "data-pipeline"
MODEL_DIR = PROJECT_ROOT / "model"
TRAINING_HISTORY_FILE = PROJECT_ROOT / "webapp" / "backend" / "app" / "training_history.json"

JOBS: Dict[str, Dict[str, Any]] = {}


def get_torch_device() -> torch.device:
    """Returns Apple Silicon MPS device if available, else CUDA or CPU."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    elif torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def get_available_training_config() -> Dict[str, Any]:
    """Returns configurable options and default parameters for each model family."""
    return {
        "models": [
            {
                "id": "xgboost",
                "name": "XGBoost",
                "family": "XGBoost",
                "type": "Supervised Gradient Boosted Trees",
                "description": "High-speed tree ensemble with regularized loss, highly effective on tabular traffic data.",
                "parameters": [
                    {"key": "n_estimators", "label": "Number of Estimators", "type": "int", "default": 100, "min": 20, "max": 300, "step": 10},
                    {"key": "max_depth", "label": "Max Tree Depth", "type": "int", "default": 6, "min": 2, "max": 12, "step": 1},
                    {"key": "learning_rate", "label": "Learning Rate (eta)", "type": "float", "default": 0.1, "min": 0.01, "max": 0.5, "step": 0.01},
                    {"key": "subsample", "label": "Subsample Ratio", "type": "float", "default": 0.9, "min": 0.5, "max": 1.0, "step": 0.05},
                    {"key": "random_state", "label": "Random Seed", "type": "int", "default": 42, "min": 1, "max": 9999, "step": 1}
                ]
            },
            {
                "id": "mlp",
                "name": "MLP (Multi-Layer Perceptron)",
                "family": "MLP",
                "type": "Deep Feedforward Neural Network",
                "description": "PyTorch deep neural network with Batch Normalization, ReLU, and Dropout layers.",
                "parameters": [
                    {"key": "epochs", "label": "Training Epochs", "type": "int", "default": 10, "min": 2, "max": 40, "step": 1},
                    {"key": "batch_size", "label": "Batch Size", "type": "int", "default": 512, "min": 128, "max": 1024, "step": 128},
                    {"key": "hidden_dim", "label": "Hidden Layer Units", "type": "int", "default": 128, "min": 32, "max": 256, "step": 32},
                    {"key": "learning_rate", "label": "Learning Rate", "type": "float", "default": 0.001, "min": 0.0001, "max": 0.01, "step": 0.0005},
                    {"key": "dropout_rate", "label": "Dropout Rate", "type": "float", "default": 0.2, "min": 0.0, "max": 0.5, "step": 0.05},
                    {"key": "random_state", "label": "Random Seed", "type": "int", "default": 42, "min": 1, "max": 9999, "step": 1}
                ]
            },
            {
                "id": "autoencoder",
                "name": "Autoencoder Anomaly Detector",
                "family": "Autoencoder",
                "type": "Unsupervised Deep Reconstruction",
                "description": "Trained solely on benign traffic. Samples exceeding reconstruction error threshold are flagged as intrusions.",
                "parameters": [
                    {"key": "epochs", "label": "Reconstruction Epochs", "type": "int", "default": 10, "min": 2, "max": 30, "step": 1},
                    {"key": "batch_size", "label": "Batch Size", "type": "int", "default": 512, "min": 128, "max": 1024, "step": 128},
                    {"key": "learning_rate", "label": "Learning Rate", "type": "float", "default": 0.001, "min": 0.0001, "max": 0.01, "step": 0.0005},
                    {"key": "threshold_percentile", "label": "Alert Threshold Percentile (%)", "type": "float", "default": 95.0, "min": 80.0, "max": 99.5, "step": 0.5},
                    {"key": "random_state", "label": "Random Seed", "type": "int", "default": 42, "min": 1, "max": 9999, "step": 1}
                ]
            },
            {
                "id": "isolation_forest",
                "name": "Isolation Forest",
                "family": "Isolation Forest",
                "type": "Unsupervised Tree Partitioning",
                "description": "Isolates anomalous data points through random recursive space partitioning without label supervision.",
                "parameters": [
                    {"key": "n_estimators", "label": "Isolation Trees", "type": "int", "default": 80, "min": 20, "max": 200, "step": 10},
                    {"key": "contamination", "label": "Expected Contamination / Anomaly Rate", "type": "float", "default": 0.15, "min": 0.01, "max": 0.40, "step": 0.01},
                    {"key": "random_state", "label": "Random Seed", "type": "int", "default": 42, "min": 1, "max": 9999, "step": 1}
                ]
            }
        ],
        "datasets": [
            {
                "id": "common",
                "name": "Common Harmonized Dataset",
                "description": "Combined cross-dataset flow features from NSL-KDD and UNSW-NB15 (201k train, 104k test)",
                "features_count": 10
            },
            {
                "id": "nsl-kdd",
                "name": "NSL-KDD (Harmonized)",
                "description": "Standard benchmark with harmonized transport and flow features (125k train, 22k test)",
                "features_count": 10
            },
            {
                "id": "unsw-nb15",
                "name": "UNSW-NB15 (Harmonized)",
                "description": "Modern synthetic and real traffic benchmark (175k train, 82k test)",
                "features_count": 10
            }
        ],
        "target_types": [
            {
                "id": "binary",
                "name": "Binary Classification",
                "description": "2-class intrusion detection (Normal vs Attack)",
                "classes": ["Normal", "Attack"]
            },
            {
                "id": "multiclass",
                "name": "Multiclass Attack Categorization",
                "description": "7-class taxonomy (Normal, DoS/DDoS, Exploit/U2R, Brute-force/R2L, Probe/Recon, Generic/Fuzzer, Botnet/Backdoor)",
                "classes": [
                    "Botnet/Backdoor",
                    "Brute-force/R2L",
                    "DoS/DDoS",
                    "Exploit/U2R",
                    "Generic/Fuzzer",
                    "Normal",
                    "Probe/Recon"
                ]
            }
        ]
    }


def load_dataset_arrays(dataset_id: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str], pd.DataFrame]:
    """Loads clean feature matrices and binary target arrays for training and testing."""
    if dataset_id == "common":
        base = DATA_PIPELINE / "common" / "output" / "feature_engineering"
        train_feat = pd.read_csv(base / "train" / "features.csv").drop(columns=["record_id"], errors="ignore")
        train_lbl = pd.read_csv(base / "train" / "labels.csv", usecols=["label_binary"])["label_binary"].values
        test_feat = pd.read_csv(base / "test" / "features.csv").drop(columns=["record_id"], errors="ignore")
        test_lbl = pd.read_csv(base / "test" / "labels.csv", usecols=["label_binary"])["label_binary"].values
        test_meta = pd.read_csv(base / "test" / "metadata.csv")
        feature_names = list(train_feat.columns)
        return (
            np.array(train_feat.values, dtype=np.float32, copy=True),
            np.array(train_lbl, dtype=np.int64, copy=True),
            np.array(test_feat.values, dtype=np.float32, copy=True),
            np.array(test_lbl, dtype=np.int64, copy=True),
            feature_names,
            test_meta
        )

    elif dataset_id == "nsl-kdd":
        base = DATA_PIPELINE / "NSL-KDD" / "output" / "harmonized"
        feat_df = pd.read_csv(base / "features.csv")
        lbl_df = pd.read_csv(base / "labels.csv", usecols=["label_binary"])
        meta_df = pd.read_csv(base / "metadata.csv")

        train_mask = (meta_df["source_split"].str.lower() == "train").values
        test_mask = (meta_df["source_split"].str.lower() == "test").values

        num_cols = ["duration", "bytes_forward", "bytes_backward"]
        for c in num_cols:
            feat_df[c] = np.log1p(np.maximum(0, feat_df[c].fillna(0).values))
        proto_dummies = pd.get_dummies(feat_df["protocol"].fillna("other"), prefix="proto", dtype=float)
        X_df = pd.concat([feat_df[num_cols], proto_dummies], axis=1)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_df)
        y = lbl_df["label_binary"].values.astype(np.int64)

        return (
            np.array(X_scaled[train_mask], dtype=np.float32, copy=True),
            np.array(y[train_mask], dtype=np.int64, copy=True),
            np.array(X_scaled[test_mask], dtype=np.float32, copy=True),
            np.array(y[test_mask], dtype=np.int64, copy=True),
            list(X_df.columns),
            meta_df[test_mask].reset_index(drop=True)
        )

    else: # unsw-nb15
        base = DATA_PIPELINE / "UNSW-NB15" / "output" / "harmonized"
        feat_df = pd.read_csv(base / "features.csv")
        lbl_df = pd.read_csv(base / "labels.csv", usecols=["label_binary"])
        meta_df = pd.read_csv(base / "metadata.csv")

        train_mask = (meta_df["source_split"].str.lower() == "train").values
        test_mask = (meta_df["source_split"].str.lower() == "test").values

        num_cols = ["duration", "bytes_forward", "bytes_backward"]
        for c in num_cols:
            feat_df[c] = np.log1p(np.maximum(0, feat_df[c].fillna(0).values))
        proto_dummies = pd.get_dummies(feat_df["protocol"].fillna("other"), prefix="proto", dtype=float)
        X_df = pd.concat([feat_df[num_cols], proto_dummies], axis=1)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_df)
        y = lbl_df["label_binary"].values.astype(np.int64)

        return (
            np.array(X_scaled[train_mask], dtype=np.float32, copy=True),
            np.array(y[train_mask], dtype=np.int64, copy=True),
            np.array(X_scaled[test_mask], dtype=np.float32, copy=True),
            np.array(y[test_mask], dtype=np.int64, copy=True),
            list(X_df.columns),
            meta_df[test_mask].reset_index(drop=True)
        )


def calculate_metrics_dict(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    """Calculates evaluation metrics and confusion matrix."""
    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "false_positive_rate": fpr,
        "confusion_matrix": cm.tolist(),
        "classes": ["Normal", "Attack"]
    }


# PyTorch Neural Architectures
class TorchMLP(nn.Module):
    def __init__(self, in_dim: int, hidden_dim: int = 128, dropout: float = 0.2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.BatchNorm1d(hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 2)
        )

    def forward(self, x):
        return self.net(x)


class TorchAutoencoder(nn.Module):
    def __init__(self, in_dim: int):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(in_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 8)
        )
        self.decoder = nn.Sequential(
            nn.Linear(8, 16),
            nn.ReLU(),
            nn.Linear(16, 32),
            nn.ReLU(),
            nn.Linear(32, in_dim)
        )

    def forward(self, x):
        return self.decoder(self.encoder(x))


class XGBProgressCallback(xgb.callback.TrainingCallback):
    def __init__(self, n_estimators: int, cb: Optional[Callable]):
        self.n_estimators = n_estimators
        self.cb = cb

    def after_iteration(self, model, epoch, evals_log):
        if self.cb:
            pct = 10 + int((epoch + 1) / self.n_estimators * 75)
            self.cb(pct, "Fitting Trees", f"Boosting tree {epoch + 1}/{self.n_estimators}", epoch=epoch + 1)
        return False


def train_model_pipeline(
    family: str,
    dataset_id: str,
    params: Dict[str, Any],
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """Orchestrates live model training, evaluation, persistence, and registration."""
    start_time = time.time()
    iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    family_lower = family.lower()

    if progress_callback:
        progress_callback(5, "Loading Dataset", "Reading feature matrices and target splits...")

    X_train, y_train, X_test, y_test, feat_names, meta_test = load_dataset_arrays(dataset_id)
    input_dim = X_train.shape[1]

    run_id = f"{family_lower}-{dataset_id}-{iso_str}"
    save_dir = MODEL_DIR / (family_lower if family_lower in ["xgboost", "mlp", "autoencoder"] else "isolation-forest") / "backup" / run_id
    save_dir.mkdir(parents=True, exist_ok=True)

    model_name_display = f"{family} ({dataset_id.upper()} Live Train)"
    device = get_torch_device()

    if family_lower == "xgboost":
        n_est = int(params.get("n_estimators", 100))
        depth = int(params.get("max_depth", 6))
        lr = float(params.get("learning_rate", 0.1))
        sub = float(params.get("subsample", 0.9))
        seed = int(params.get("random_state", 42))

        cb_list = [XGBProgressCallback(n_est, progress_callback)] if progress_callback else []
        clf = XGBClassifier(
            n_estimators=n_est,
            max_depth=depth,
            learning_rate=lr,
            subsample=sub,
            random_state=seed,
            n_jobs=-1,
            eval_metric="logloss",
            callbacks=cb_list
        )
        clf.fit(X_train, y_train)

        if progress_callback:
            progress_callback(88, "Evaluating", "Running predictions on evaluation test split...")
        y_pred = clf.predict(X_test)
        joblib.dump(clf, save_dir / "xgboost_model.joblib")

    elif family_lower == "mlp":
        epochs = int(params.get("epochs", 10))
        batch_size = max(128, int(params.get("batch_size", 512)))
        hidden_dim = int(params.get("hidden_dim", 128))
        lr = float(params.get("learning_rate", 0.001))
        dropout = float(params.get("dropout_rate", 0.2))
        seed = int(params.get("random_state", 42))

        torch.manual_seed(seed)
        net = TorchMLP(input_dim, hidden_dim, dropout).to(device)
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(net.parameters(), lr=lr)

        t_x = torch.from_numpy(np.ascontiguousarray(X_train, dtype=np.float32))
        t_y = torch.from_numpy(np.ascontiguousarray(y_train, dtype=np.int64))
        train_ds = TensorDataset(t_x, t_y)
        loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

        net.train()
        for epoch in range(epochs):
            epoch_loss = 0.0
            batches = 0
            for bx, by in loader:
                bx, by = bx.to(device), by.to(device)
                optimizer.zero_grad()
                out = net(bx)
                loss = criterion(out, by)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                batches += 1

            avg_loss = epoch_loss / max(1, batches)
            if progress_callback:
                pct = 10 + int((epoch + 1) / epochs * 75)
                progress_callback(pct, "Training Neural Network", f"Epoch {epoch + 1}/{epochs} - Batch Loss: {avg_loss:.4f}", epoch=epoch + 1, loss=avg_loss)

        if progress_callback:
            progress_callback(88, "Evaluating", "Computing forward inference on test evaluation split...")

        net.eval()
        with torch.no_grad():
            test_tensor = torch.from_numpy(np.ascontiguousarray(X_test, dtype=np.float32)).to(device)
            test_out = net(test_tensor)
            y_pred = torch.argmax(test_out, dim=1).cpu().numpy()
        torch.save(net.state_dict(), save_dir / "model.pth")

    elif family_lower == "autoencoder":
        epochs = int(params.get("epochs", 10))
        batch_size = max(128, int(params.get("batch_size", 512)))
        lr = float(params.get("learning_rate", 0.001))
        pct = float(params.get("threshold_percentile", 95.0))
        seed = int(params.get("random_state", 42))

        torch.manual_seed(seed)
        normal_idx = np.where(y_train == 0)[0]
        X_train_norm = X_train[normal_idx]

        ae = TorchAutoencoder(input_dim).to(device)
        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(ae.parameters(), lr=lr)

        t_norm = torch.from_numpy(np.ascontiguousarray(X_train_norm, dtype=np.float32))
        train_ds = TensorDataset(t_norm)
        loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

        ae.train()
        for epoch in range(epochs):
            epoch_loss = 0.0
            batches = 0
            for (bx,) in loader:
                bx = bx.to(device)
                optimizer.zero_grad()
                recon = ae(bx)
                loss = criterion(recon, bx)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                batches += 1

            avg_loss = epoch_loss / max(1, batches)
            if progress_callback:
                pct = 10 + int((epoch + 1) / epochs * 75)
                progress_callback(pct, "Training Autoencoder", f"Epoch {epoch + 1}/{epochs} - Recon Loss: {avg_loss:.4f}", epoch=epoch + 1, loss=avg_loss)

        if progress_callback:
            progress_callback(88, "Evaluating", "Calculating normal error threshold and anomaly residuals...")

        ae.eval()
        with torch.no_grad():
            norm_tensor = torch.from_numpy(np.ascontiguousarray(X_train_norm, dtype=np.float32)).to(device)
            norm_recon = ae(norm_tensor)
            normal_errors = torch.mean((norm_tensor - norm_recon) ** 2, dim=1).cpu().numpy()
            threshold = float(np.percentile(normal_errors, pct))

            test_tensor = torch.from_numpy(np.ascontiguousarray(X_test, dtype=np.float32)).to(device)
            test_recon = ae(test_tensor)
            test_errors = torch.mean((test_tensor - test_recon) ** 2, dim=1).cpu().numpy()
            y_pred = (test_errors > threshold).astype(int)

        torch.save(ae.state_dict(), save_dir / "autoencoder.pth")
        params["computed_threshold"] = threshold

    elif family_lower == "isolation_forest":
        n_est = int(params.get("n_estimators", 80))
        contam = float(params.get("contamination", 0.15))
        seed = int(params.get("random_state", 42))

        if progress_callback:
            progress_callback(20, "Partitioning Space", f"Fitting {n_est} isolation trees...")

        train_sub = X_train if len(X_train) <= 100000 else X_train[:100000]
        clf = IsolationForest(n_estimators=n_est, contamination=contam, random_state=seed, n_jobs=-1)
        clf.fit(train_sub)

        if progress_callback:
            progress_callback(88, "Evaluating", "Scoring test instances for isolation outliers...")

        raw_pred = clf.predict(X_test)
        y_pred = np.where(raw_pred == -1, 1, 0)
        joblib.dump(clf, save_dir / "isolation_forest.joblib")

    else:
        raise ValueError(f"Unsupported model family: {family}")

    if progress_callback:
        progress_callback(95, "Compiling Metrics", "Compiling confusion matrices and threat subsets...")

    # Primary Overall Test Metrics
    primary_metrics = calculate_metrics_dict(y_test, y_pred)

    # Subsets calculation if dataset is Common Harmonized
    kdd_metrics = {}
    kdd21_metrics = {}
    unsw_metrics = {}
    if dataset_id == "common" and "source_dataset" in meta_test.columns:
        kdd_mask = (meta_test["source_dataset"] == "NSL-KDD").values
        if np.any(kdd_mask):
            kdd_metrics = calculate_metrics_dict(y_test[kdd_mask], y_pred[kdd_mask])

        kdd21_mask = (meta_test["is_kddtest21_view"] == True).values if "is_kddtest21_view" in meta_test.columns else np.zeros(len(y_test), dtype=bool)
        if np.any(kdd21_mask):
            kdd21_metrics = calculate_metrics_dict(y_test[kdd21_mask], y_pred[kdd21_mask])

        unsw_mask = (meta_test["source_dataset"] == "UNSW-NB15").values
        if np.any(unsw_mask):
            unsw_metrics = calculate_metrics_dict(y_test[unsw_mask], y_pred[unsw_mask])
    else:
        kdd_metrics = primary_metrics
        kdd21_metrics = primary_metrics

    elapsed_time = round(time.time() - start_time, 2)

    eval_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name_display,
        "family": family,
        "run_id": run_id,
        "mode": "binary",
        "dataset": dataset_id,
        "hyperparameters": params,
        "kddtest_metrics": kdd_metrics,
        "kddtest21_metrics": kdd21_metrics,
        "common_test_metrics": primary_metrics if dataset_id == "common" else None,
        "unsw_test_metrics": unsw_metrics if dataset_id == "common" else None,
        "confusion_matrix_kddtest": kdd_metrics.get("confusion_matrix", primary_metrics.get("confusion_matrix", [])),
        "confusion_matrix_kddtest21": kdd21_metrics.get("confusion_matrix", primary_metrics.get("confusion_matrix", [])),
        "classes": ["Normal", "Attack"],
        "elapsed_seconds": elapsed_time
    }

    with open(save_dir / "evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(eval_data, f, indent=2)

    _append_training_history({
        "timestamp": eval_data["timestamp"],
        "run_id": run_id,
        "family": family,
        "dataset": dataset_id,
        "accuracy": primary_metrics["accuracy"],
        "f1": primary_metrics["f1"],
        "balanced_accuracy": primary_metrics["balanced_accuracy"],
        "elapsed_seconds": elapsed_time,
        "hyperparameters": params
    })

    if progress_callback:
        progress_callback(100, "Completed", "Training successfully completed.", epoch=None, loss=None)

    return eval_data


def start_training_job(
    family: str,
    dataset_id: str,
    params: Dict[str, Any],
    target_type: str = "binary",
    on_finish_cache_clear: Optional[Callable] = None
) -> str:
    """Spawns an asynchronous background training job and returns job_id."""
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    total_steps = int(params.get("epochs", params.get("n_estimators", 10)))

    JOBS[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "family": family,
        "dataset": dataset_id,
        "mode": target_type,
        "progress": 0,
        "phase": "Initializing",
        "current_epoch": 0,
        "total_epochs": total_steps,
        "current_loss": None,
        "message": "Initializing background training worker...",
        "start_time": time.time(),
        "elapsed_seconds": 0.0,
        "result": None,
        "error": None
    }

    def runner():
        start_ts = time.time()
        import subprocess
        import sys

        cmd = [
            sys.executable,
            "-m",
            "app.training_worker",
            "--family",
            family,
            "--dataset",
            dataset_id,
            "--params",
            json.dumps(params),
            "--target_type",
            target_type
        ]

        try:
            JOBS[job_id]["status"] = "training"
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT / "webapp" / "backend"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            final_result = None
            for line in proc.stdout:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    msg = json.loads(line_str)
                    if msg.get("type") == "progress":
                        if job_id in JOBS:
                            JOBS[job_id]["progress"] = msg.get("progress", 0)
                            JOBS[job_id]["phase"] = msg.get("phase", "Training")
                            JOBS[job_id]["message"] = msg.get("message", "")
                            JOBS[job_id]["elapsed_seconds"] = round(time.time() - start_ts, 1)
                            if msg.get("epoch") is not None:
                                JOBS[job_id]["current_epoch"] = msg["epoch"]
                            if msg.get("loss") is not None:
                                JOBS[job_id]["current_loss"] = msg["loss"]
                    elif msg.get("type") == "result":
                        final_result = msg.get("data")
                except json.JSONDecodeError:
                    pass

            proc.wait()
            stderr_out = proc.stderr.read()

            if proc.returncode != 0:
                raise RuntimeError(stderr_out.strip() or f"Process failed with exit code {proc.returncode}")

            if on_finish_cache_clear:
                on_finish_cache_clear()

            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["progress"] = 100
            JOBS[job_id]["phase"] = "Completed"
            JOBS[job_id]["message"] = f"Training completed successfully in {round(time.time() - start_ts, 1)}s."
            JOBS[job_id]["result"] = final_result
        except Exception as ex:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(ex)
            JOBS[job_id]["message"] = f"Training error: {str(ex)}"

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return job_id


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Retrieves live job execution state."""
    job = JOBS.get(job_id)
    if not job:
        return {"status": "not_found", "error": "Job ID does not exist"}
    if job["status"] == "training":
        job["elapsed_seconds"] = round(time.time() - job["start_time"], 1)
    return job


def _append_training_history(entry: Dict[str, Any]):
    """Stores the latest training runs in history JSON."""
    history = []
    if TRAINING_HISTORY_FILE.exists():
        try:
            with open(TRAINING_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    history.insert(0, entry)
    history = history[:30]
    with open(TRAINING_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def get_training_history() -> List[Dict[str, Any]]:
    """Retrieves recent training run logs with hyperparameter records."""
    if TRAINING_HISTORY_FILE.exists():
        try:
            with open(TRAINING_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []
