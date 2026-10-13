"""
Independent Training Worker Subprocess Script
Executes training for a given architecture and dataset in an isolated Python process.
Communicates real-time progress to stdout via structured JSON lines (JSONL).
This guarantees 100% process and memory isolation, preventing OpenMP / libomp / MPS symbol collisions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

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

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PIPELINE = PROJECT_ROOT / "data-pipeline"
MODEL_DIR = PROJECT_ROOT / "model"
TRAINING_HISTORY_FILE = PROJECT_ROOT / "webapp" / "backend" / "app" / "training_history.json"


def send_progress(pct: int, phase: str, message: str, epoch: int | None = None, loss: float | None = None):
    """Outputs progress update line to stdout."""
    payload = {
        "type": "progress",
        "progress": pct,
        "phase": phase,
        "message": message,
        "epoch": epoch,
        "loss": round(loss, 4) if loss is not None else None,
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


MULTICLASS_CATEGORIES = [
    "Botnet/Backdoor",
    "Brute-force/R2L",
    "DoS/DDoS",
    "Exploit/U2R",
    "Generic/Fuzzer",
    "Normal",
    "Probe/Recon",
]
CATEGORY_TO_IDX = {cat: i for i, cat in enumerate(MULTICLASS_CATEGORIES)}


def load_dataset_arrays(dataset_id: str, target_type: str = "binary"):
    """Loads clean feature matrices and target arrays (binary or multiclass)."""
    if dataset_id == "common":
        base = DATA_PIPELINE / "common" / "output" / "feature_engineering"
        train_feat = pd.read_csv(base / "train" / "features.csv").drop(columns=["record_id"], errors="ignore")
        test_feat = pd.read_csv(base / "test" / "features.csv").drop(columns=["record_id"], errors="ignore")
        train_lbl_df = pd.read_csv(base / "train" / "labels.csv", low_memory=False)
        test_lbl_df = pd.read_csv(base / "test" / "labels.csv", low_memory=False)
        test_meta = pd.read_csv(base / "test" / "metadata.csv")
        feature_names = list(train_feat.columns)

        if target_type == "multiclass":
            train_cats = train_lbl_df["attack_category"].fillna("Normal").astype(str)
            test_cats = test_lbl_df["attack_category"].fillna("Normal").astype(str)
            y_train = np.array([CATEGORY_TO_IDX.get(c, 5) for c in train_cats], dtype=np.int64)
            y_test = np.array([CATEGORY_TO_IDX.get(c, 5) for c in test_cats], dtype=np.int64)
            classes = MULTICLASS_CATEGORIES
        else:
            y_train = train_lbl_df["label_binary"].values.astype(np.int64)
            y_test = test_lbl_df["label_binary"].values.astype(np.int64)
            classes = ["Normal", "Attack"]

        return (
            np.ascontiguousarray(train_feat.to_numpy(dtype=np.float32)),
            np.ascontiguousarray(y_train),
            np.ascontiguousarray(test_feat.to_numpy(dtype=np.float32)),
            np.ascontiguousarray(y_test),
            feature_names,
            test_meta,
            classes,
        )

    elif dataset_id == "nsl-kdd":
        base = DATA_PIPELINE / "NSL-KDD" / "output" / "harmonized"
        feat_df = pd.read_csv(base / "features.csv")
        lbl_df = pd.read_csv(base / "labels.csv", low_memory=False)
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

        if target_type == "multiclass":
            cats = lbl_df["attack_category"].fillna("Normal").astype(str)
            y = np.array([CATEGORY_TO_IDX.get(c, 5) for c in cats], dtype=np.int64)
            classes = MULTICLASS_CATEGORIES
        else:
            y = lbl_df["label_binary"].values.astype(np.int64)
            classes = ["Normal", "Attack"]

        return (
            np.ascontiguousarray(X_scaled[train_mask], dtype=np.float32),
            np.ascontiguousarray(y[train_mask]),
            np.ascontiguousarray(X_scaled[test_mask], dtype=np.float32),
            np.ascontiguousarray(y[test_mask]),
            list(X_df.columns),
            meta_df[test_mask].reset_index(drop=True),
            classes,
        )

    else:  # unsw-nb15
        base = DATA_PIPELINE / "UNSW-NB15" / "output" / "harmonized"
        feat_df = pd.read_csv(base / "features.csv")
        lbl_df = pd.read_csv(base / "labels.csv", low_memory=False)
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

        if target_type == "multiclass":
            cats = lbl_df["attack_category"].fillna("Normal").astype(str)
            y = np.array([CATEGORY_TO_IDX.get(c, 5) for c in cats], dtype=np.int64)
            classes = MULTICLASS_CATEGORIES
        else:
            y = lbl_df["label_binary"].values.astype(np.int64)
            classes = ["Normal", "Attack"]

        return (
            np.ascontiguousarray(X_scaled[train_mask], dtype=np.float32),
            np.ascontiguousarray(y[train_mask]),
            np.ascontiguousarray(X_scaled[test_mask], dtype=np.float32),
            np.ascontiguousarray(y[test_mask]),
            list(X_df.columns),
            meta_df[test_mask].reset_index(drop=True),
            classes,
        )


def calculate_metrics_dict(y_true: np.ndarray, y_pred: np.ndarray, classes: list[str] | None = None) -> Dict[str, Any]:
    """Calculates evaluation metrics and confusion matrix for binary or multiclass tasks."""
    num_classes = len(classes) if classes else len(np.unique(np.concatenate([y_true, y_pred])))
    labels_idx = list(range(num_classes)) if classes else None
    cm = confusion_matrix(y_true, y_pred, labels=labels_idx)

    if num_classes == 2 and cm.shape == (2, 2):
        tn, fp, fn, tp = cm.ravel()
        fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
        classes_out = classes or ["Normal", "Attack"]
    else:
        # Multiclass FPR: FP / (FP + TN) across non-normal classes vs normal class (idx 5 is Normal)
        normal_idx = 5 if classes and "Normal" in classes and classes.index("Normal") == 5 else 0
        fp = float(np.sum(cm[normal_idx, :]) - cm[normal_idx, normal_idx])
        tn = float(np.sum(cm) - np.sum(cm[normal_idx, :]) - np.sum(cm[:, normal_idx]) + cm[normal_idx, normal_idx])
        fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
        classes_out = classes or [f"Class {i}" for i in range(num_classes)]

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "false_positive_rate": fpr,
        "confusion_matrix": cm.tolist(),
        "classes": classes_out,
    }


class SubprocessXGBCallback:
    def __init__(self, n_est: int):
        self.n_est = n_est

    def after_iteration(self, model, epoch, evals_log):
        pct = 10 + int((epoch + 1) / self.n_est * 75)
        send_progress(pct, "Fitting Trees", f"Boosting tree {epoch + 1}/{self.n_est}", epoch=epoch + 1)
        return False


def execute_training(family: str, dataset_id: str, params: Dict[str, Any], target_type: str = "binary"):
    start_time = time.time()
    iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    family_lower = family.lower().replace(" ", "_").replace("-", "_")

    send_progress(5, "Loading Dataset", f"Reading feature matrices and {target_type} target splits...")
    X_train, y_train, X_test, y_test, feat_names, meta_test, classes = load_dataset_arrays(dataset_id, target_type=target_type)
    input_dim = X_train.shape[1]
    num_classes = len(classes)

    run_id = f"{family_lower}-{dataset_id}-{target_type}-{iso_str}"
    target_folder = family_lower if family_lower in ["xgboost", "mlp", "autoencoder"] else "isolation-forest"
    save_dir = MODEL_DIR / target_folder / "backup" / run_id
    save_dir.mkdir(parents=True, exist_ok=True)

    model_name_display = f"{family} ({dataset_id.upper()} {target_type.capitalize()})"

    if family_lower == "xgboost":
        from xgboost import XGBClassifier
        from xgboost.callback import TrainingCallback

        n_est = int(params.get("n_estimators", 100))
        depth = int(params.get("max_depth", 6))
        lr = float(params.get("learning_rate", 0.1))
        sub = float(params.get("subsample", 0.9))
        seed = int(params.get("random_state", 42))

        class GlobalXGBCallback(TrainingCallback):
            def __init__(self, n_e: int):
                self.n_e = n_e

            def after_iteration(self, model, epoch, evals_log):
                pct = 10 + int((epoch + 1) / self.n_e * 75)
                send_progress(pct, "Fitting Trees", f"Boosting tree {epoch + 1}/{self.n_e}", epoch=epoch + 1)
                return False

        cb_obj = GlobalXGBCallback(n_est)
        eval_metric = "mlogloss" if target_type == "multiclass" else "logloss"
        objective = "multi:softprob" if target_type == "multiclass" else "binary:logistic"

        clf = XGBClassifier(
            n_estimators=n_est,
            max_depth=depth,
            learning_rate=lr,
            subsample=sub,
            random_state=seed,
            n_jobs=-1,
            objective=objective,
            eval_metric=eval_metric,
            callbacks=[cb_obj],
        )
        clf.fit(X_train, y_train)

        send_progress(88, "Evaluating", "Running predictions on evaluation test split...")
        y_pred = clf.predict(X_test)
        # Clear runtime callback object before serialization
        clf.set_params(callbacks=[])
        joblib.dump(clf, save_dir / "xgboost_model.joblib")

    elif family_lower == "mlp":
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        epochs = int(params.get("epochs", 10))
        batch_size = max(128, int(params.get("batch_size", 512)))
        hidden_dim = int(params.get("hidden_dim", 128))
        lr = float(params.get("learning_rate", 0.001))
        dropout = float(params.get("dropout_rate", 0.2))
        seed = int(params.get("random_state", 42))

        torch.manual_seed(seed)
        device = torch.device("cpu")

        class TorchMLP(nn.Module):
            def __init__(self, in_d, h_d, drop, out_d):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(in_d, h_d),
                    nn.BatchNorm1d(h_d),
                    nn.ReLU(),
                    nn.Dropout(drop),
                    nn.Linear(h_d, h_d // 2),
                    nn.BatchNorm1d(h_d // 2),
                    nn.ReLU(),
                    nn.Dropout(drop),
                    nn.Linear(h_d // 2, out_d),
                )

            def forward(self, x):
                return self.net(x)

        net = TorchMLP(input_dim, hidden_dim, dropout, num_classes).to(device)
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(net.parameters(), lr=lr)

        t_x = torch.from_numpy(X_train)
        t_y = torch.from_numpy(y_train)
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
            pct = 10 + int((epoch + 1) / epochs * 75)
            send_progress(pct, "Training Neural Network", f"Epoch {epoch + 1}/{epochs} - Batch Loss: {avg_loss:.4f}", epoch=epoch + 1, loss=avg_loss)

        send_progress(88, "Evaluating", "Computing forward inference on test evaluation split...")
        net.eval()
        with torch.no_grad():
            test_tensor = torch.from_numpy(X_test).to(device)
            test_out = net(test_tensor)
            y_pred = torch.argmax(test_out, dim=1).cpu().numpy()
        torch.save(net.state_dict(), save_dir / "model.pth")

    elif family_lower == "autoencoder":
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        epochs = int(params.get("epochs", 10))
        batch_size = max(128, int(params.get("batch_size", 512)))
        lr = float(params.get("learning_rate", 0.001))
        pct = float(params.get("threshold_percentile", 95.0))
        seed = int(params.get("random_state", 42))

        torch.manual_seed(seed)
        device = torch.device("cpu")

        class TorchAutoencoder(nn.Module):
            def __init__(self, in_d):
                super().__init__()
                self.encoder = nn.Sequential(
                    nn.Linear(in_d, 32),
                    nn.ReLU(),
                    nn.Linear(32, 16),
                    nn.ReLU(),
                    nn.Linear(16, 8),
                )
                self.decoder = nn.Sequential(
                    nn.Linear(8, 16),
                    nn.ReLU(),
                    nn.Linear(16, 32),
                    nn.ReLU(),
                    nn.Linear(32, in_d),
                )

            def forward(self, x):
                return self.decoder(self.encoder(x))

        normal_idx = np.where(y_train == (5 if target_type == "multiclass" else 0))[0]
        X_train_norm = X_train[normal_idx]

        ae = TorchAutoencoder(input_dim).to(device)
        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(ae.parameters(), lr=lr)

        t_norm = torch.from_numpy(X_train_norm)
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
            pct_prog = 10 + int((epoch + 1) / epochs * 75)
            send_progress(pct_prog, "Training Autoencoder", f"Epoch {epoch + 1}/{epochs} - Recon Loss: {avg_loss:.4f}", epoch=epoch + 1, loss=avg_loss)

        send_progress(88, "Evaluating", "Calculating normal error threshold and anomaly residuals...")
        ae.eval()
        with torch.no_grad():
            norm_tensor = torch.from_numpy(X_train_norm).to(device)
            norm_recon = ae(norm_tensor)
            normal_errors = torch.mean((norm_tensor - norm_recon) ** 2, dim=1).cpu().numpy()
            threshold = float(np.percentile(normal_errors, pct))

            test_tensor = torch.from_numpy(X_test).to(device)
            test_recon = ae(test_tensor)
            test_errors = torch.mean((test_tensor - test_recon) ** 2, dim=1).cpu().numpy()
            y_pred = (test_errors > threshold).astype(int)

        torch.save(ae.state_dict(), save_dir / "autoencoder.pth")
        params["computed_threshold"] = threshold

    elif family_lower in ["isolation_forest", "isolationforest"]:
        from sklearn.ensemble import IsolationForest

        n_est = int(params.get("n_estimators", 80))
        contam = float(params.get("contamination", 0.15))
        seed = int(params.get("random_state", 42))

        send_progress(20, "Partitioning Space", f"Fitting {n_est} isolation trees...")
        train_sub = X_train if len(X_train) <= 100000 else X_train[:100000]
        clf = IsolationForest(n_estimators=n_est, contamination=contam, random_state=seed, n_jobs=-1)
        clf.fit(train_sub)

        send_progress(88, "Evaluating", "Scoring test instances for isolation outliers...")
        raw_pred = clf.predict(X_test)
        y_pred = np.where(raw_pred == -1, 1, 0)
        joblib.dump(clf, save_dir / "isolation_forest.joblib")

    else:
        raise ValueError(f"Unsupported model family: {family}")

    send_progress(95, "Compiling Metrics", "Compiling confusion matrices and threat subsets...")
    primary_metrics = calculate_metrics_dict(y_test, y_pred, classes=classes)

    kddtest_metrics = None
    kddtest21_metrics = None
    common_test_metrics = None
    unsw_test_metrics = None

    if dataset_id == "common" and "source_dataset" in meta_test.columns:
        nsl_mask = meta_test["source_dataset"].str.upper() == "NSL-KDD"
        if nsl_mask.sum() > 0:
            kddtest_metrics = calculate_metrics_dict(y_test[nsl_mask], y_pred[nsl_mask], classes=classes)
            kdd21_mask = nsl_mask & (meta_test.get("difficulty_level", pd.Series(99, index=meta_test.index)) < 21)
            if kdd21_mask.sum() > 0:
                kddtest21_metrics = calculate_metrics_dict(y_test[kdd21_mask], y_pred[kdd21_mask], classes=classes)

        unsw_mask = meta_test["source_dataset"].str.upper() == "UNSW-NB15"
        if unsw_mask.sum() > 0:
            unsw_test_metrics = calculate_metrics_dict(y_test[unsw_mask], y_pred[unsw_mask], classes=classes)

        common_test_metrics = primary_metrics
    elif dataset_id == "nsl-kdd":
        kddtest_metrics = primary_metrics
    elif dataset_id == "unsw-nb15":
        unsw_test_metrics = primary_metrics

    elapsed = round(time.time() - start_time, 2)

    result_manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name_display,
        "family": family,
        "run_id": run_id,
        "mode": target_type,
        "dataset": dataset_id,
        "hyperparameters": params,
        "kddtest_metrics": kddtest_metrics or primary_metrics,
        "kddtest21_metrics": kddtest21_metrics or primary_metrics,
        "common_test_metrics": common_test_metrics,
        "unsw_test_metrics": unsw_test_metrics,
        "confusion_matrix_kddtest": (kddtest_metrics or primary_metrics)["confusion_matrix"],
        "confusion_matrix_kddtest21": (kddtest21_metrics or primary_metrics)["confusion_matrix"],
        "classes": classes,
        "elapsed_seconds": elapsed,
    }

    # Save to model manifest
    with open(save_dir / "metrics.json", "w") as f:
        json.dump(result_manifest, f, indent=2)

    # Append to training history
    _append_training_history({
        "timestamp": result_manifest["timestamp"],
        "family": family,
        "dataset": dataset_id,
        "mode": target_type,
        "run_id": run_id,
        "accuracy": (kddtest_metrics or primary_metrics).get("accuracy"),
        "f1": (kddtest_metrics or primary_metrics).get("f1"),
        "elapsed_seconds": elapsed,
        "hyperparameters": params,
    })

    send_progress(100, "Completed", "Training successfully completed.", epoch=None, loss=None)
    sys.stdout.write(json.dumps({"type": "result", "data": result_manifest}) + "\n")
    sys.stdout.flush()


def _append_training_history(entry: Dict[str, Any]):
    history = []
    if TRAINING_HISTORY_FILE.exists():
        try:
            with open(TRAINING_HISTORY_FILE, "r") as f:
                history = json.load(f)
        except Exception:
            history = []
    history.insert(0, entry)
    history = history[:40]
    TRAINING_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAINING_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--params", required=True)
    parser.add_argument("--target_type", default="binary", choices=["binary", "multiclass"])
    args = parser.parse_args()

    hyperparams = json.loads(args.params)
    execute_training(args.family, args.dataset, hyperparams, target_type=args.target_type)
