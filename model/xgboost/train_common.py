"""
XGBoost Experiment for Common Harmonized Multi-Dataset Network Intrusion Detection
Trains on unified cross-dataset flow features combining NSL-KDD and UNSW-NB15.
Evaluates across:
  1. Overall Common Test (104,876 rows)
  2. KDDTest+ Subset (22,544 rows)
  3. KDDTest-21 Subset (11,850 rows)
  4. UNSW-NB15 Test Subset (82,332 rows)
Saves checkpoints and evaluation metrics to model/xgboost/backup/ for webapp integration.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data-pipeline" / "common" / "output" / "feature_engineering"
BACKUP_DIR = PROJECT_ROOT / "model" / "xgboost" / "backup"


def load_common_datasets(data_dir: Path) -> Tuple[pd.DataFrame, np.ndarray, pd.DataFrame, np.ndarray, pd.DataFrame]:
    """Load train, test, and test metadata from common feature engineering output."""
    train_feat_path = data_dir / "train" / "features.csv"
    train_lbl_path = data_dir / "train" / "labels.csv"
    test_feat_path = data_dir / "test" / "features.csv"
    test_lbl_path = data_dir / "test" / "labels.csv"
    test_meta_path = data_dir / "test" / "metadata.csv"

    print("Loading Common Train features:", train_feat_path)
    X_train = pd.read_csv(train_feat_path).drop(columns=["record_id"], errors="ignore")
    y_train = pd.read_csv(train_lbl_path, usecols=["label_binary"])["label_binary"].values

    print("Loading Common Test features:", test_feat_path)
    X_test = pd.read_csv(test_feat_path).drop(columns=["record_id"], errors="ignore")
    y_test = pd.read_csv(test_lbl_path, usecols=["label_binary"])["label_binary"].values
    meta_test = pd.read_csv(test_meta_path)

    return X_train, y_train, X_test, y_test, meta_test


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray = None) -> Tuple[Dict[str, Any], np.ndarray]:
    """Compute binary classification metrics and confusion matrix."""
    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0

    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "false_positive_rate": fpr,
    }
    if y_prob is not None:
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_true, y_prob[:, 1]))
        except Exception:
            pass
    return metrics, cm


def plot_cm(cm: np.ndarray, classes: List[str], title: str, output_path: Path):
    """Save clean confusion matrix plot without external fancy fonts."""
    plt.figure(figsize=(5, 4))
    plt.imshow(cm, interpolation="nearest", cmap="Blues")
    plt.title(title, fontsize=11, fontweight="bold")
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes)
    plt.yticks(tick_marks, classes)

    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(
                j,
                i,
                f"{cm[i, j]:,}",
                horizontalalignment="center",
                color="white" if cm[i, j] > thresh else "black",
                fontweight="bold",
            )
    plt.ylabel("True Label")
    plt.xlabel("Predicted Label")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150)
    plt.close()


def train_single_run(
    run_idx: int,
    seed: int,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    meta_test: pd.DataFrame,
    n_estimators: int = 120,
    max_depth: int = 6,
    learning_rate: float = 0.1,
    subsample: float = 0.9,
    colsample_bytree: float = 0.9,
    backup_dir: Path = BACKUP_DIR,
) -> Dict[str, Any]:
    """Train and evaluate a single XGBoost run on the common dataset."""
    start_time = time.time()
    iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_id = f"xgboost-common-run{run_idx}-seed{seed}-{iso_str}"
    save_dir = backup_dir / run_id
    save_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=======================================================")
    print(f"Starting Run {run_idx}/5: {run_id}")
    print(f"Seed: {seed}, Trees: {n_estimators}, Depth: {max_depth}, LR: {learning_rate}")
    print(f"=======================================================")

    params = {
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "learning_rate": learning_rate,
        "subsample": subsample,
        "colsample_bytree": colsample_bytree,
        "random_state": seed,
        "n_jobs": -1,
        "objective": "binary:logistic",
        "eval_metric": "logloss",
    }

    model = XGBClassifier(**params)
    fit_start = time.time()
    model.fit(X_train, y_train)
    fit_duration = round(time.time() - fit_start, 2)
    print(f"Model fit completed in {fit_duration}s")

    # Predict on entire Common test set
    y_pred_all = model.predict(X_test)
    y_prob_all = model.predict_proba(X_test)
    common_metrics, common_cm = compute_metrics(y_test, y_pred_all, y_prob_all)

    # Subset 1: NSL-KDD Test Subset (KDDTest+)
    kdd_mask = (meta_test["source_dataset"] == "NSL-KDD").values
    kdd_metrics, kdd_cm = compute_metrics(y_test[kdd_mask], y_pred_all[kdd_mask], y_prob_all[kdd_mask])

    # Subset 2: KDDTest-21 Subset
    kdd21_mask = (meta_test["is_kddtest21_view"] == True).values if "is_kddtest21_view" in meta_test.columns else np.zeros(len(y_test), dtype=bool)
    kdd21_metrics, kdd21_cm = compute_metrics(y_test[kdd21_mask], y_pred_all[kdd21_mask], y_prob_all[kdd21_mask])

    # Subset 3: UNSW-NB15 Test Subset
    unsw_mask = (meta_test["source_dataset"] == "UNSW-NB15").values
    unsw_metrics, unsw_cm = compute_metrics(y_test[unsw_mask], y_pred_all[unsw_mask], y_prob_all[unsw_mask])

    print(f"Results Summary for Run {run_idx}:")
    print(f"  Overall Common Test (104,876 rows) -> Acc: {common_metrics['accuracy']:.4f}, F1: {common_metrics['f1']:.4f}")
    print(f"  KDDTest+ Subset     (22,544 rows)  -> Acc: {kdd_metrics['accuracy']:.4f}, F1: {kdd_metrics['f1']:.4f}")
    print(f"  KDDTest-21 Subset   (11,850 rows)  -> Acc: {kdd21_metrics['accuracy']:.4f}, F1: {kdd21_metrics['f1']:.4f}")
    print(f"  UNSW-NB15 Subset    (82,332 rows)  -> Acc: {unsw_metrics['accuracy']:.4f}, F1: {unsw_metrics['f1']:.4f}")

    # Generate Confusion Matrix Plots
    classes = ["Normal", "Attack"]
    plot_cm(kdd_cm, classes, f"XGBoost Common Run {run_idx} - KDDTest+", save_dir / "confusion_matrix_kddtest.png")
    plot_cm(kdd21_cm, classes, f"XGBoost Common Run {run_idx} - KDDTest-21", save_dir / "confusion_matrix_kddtest21.png")
    plot_cm(common_cm, classes, f"XGBoost Common Run {run_idx} - Common Test", save_dir / "confusion_matrix_common.png")
    plot_cm(unsw_cm, classes, f"XGBoost Common Run {run_idx} - UNSW Test", save_dir / "confusion_matrix_unsw.png")

    # Feature Importance
    importances = model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    top_feature_dict = {X_train.columns[i]: float(importances[i]) for i in sorted_idx}

    # Save model artifact
    model_file = save_dir / "xgboost_model.joblib"
    joblib.dump(model, model_file)

    # Threshold curve precomputation for webapp slider
    threshold_curve = []
    for th in [round(x, 2) for x in np.linspace(0.05, 0.95, 19)]:
        p_kdd = (y_prob_all[kdd_mask, 1] >= th).astype(int)
        p_kdd21 = (y_prob_all[kdd21_mask, 1] >= th).astype(int)
        threshold_curve.append({
            "threshold": th,
            "accuracy": float(accuracy_score(y_test[kdd_mask], p_kdd)),
            "precision": float(precision_score(y_test[kdd_mask], p_kdd, zero_division=0)),
            "recall": float(recall_score(y_test[kdd_mask], p_kdd, zero_division=0)),
            "f1": float(f1_score(y_test[kdd_mask], p_kdd, zero_division=0)),
            "confusion_matrix": confusion_matrix(y_test[kdd_mask], p_kdd).tolist(),
            "test21_accuracy": float(accuracy_score(y_test[kdd21_mask], p_kdd21)),
            "test21_precision": float(precision_score(y_test[kdd21_mask], p_kdd21, zero_division=0)),
            "test21_recall": float(recall_score(y_test[kdd21_mask], p_kdd21, zero_division=0)),
            "test21_f1": float(f1_score(y_test[kdd21_mask], p_kdd21, zero_division=0)),
            "test21_confusion_matrix": confusion_matrix(y_test[kdd21_mask], p_kdd21).tolist(),
        })

    total_time = round(time.time() - start_time, 2)
    eval_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": f"XGBoost (Common Harmonized Run {run_idx})",
        "family": "XGBoost",
        "mode": "binary",
        "dataset_source": "Common Harmonized (NSL-KDD + UNSW-NB15)",
        "run_idx": run_idx,
        "seed": seed,
        "classes": classes,
        "hyperparameters": params,
        "kddtest_metrics": kdd_metrics,
        "kddtest21_metrics": kdd21_metrics,
        "common_test_metrics": common_metrics,
        "unsw_test_metrics": unsw_metrics,
        "confusion_matrix_kddtest": kdd_cm.tolist(),
        "confusion_matrix_kddtest21": kdd21_cm.tolist(),
        "confusion_matrix_common": common_cm.tolist(),
        "confusion_matrix_unsw": unsw_cm.tolist(),
        "top_features": top_feature_dict,
        "threshold_curve": threshold_curve,
        "model_file": "xgboost_model.joblib",
        "elapsed_seconds": total_time,
    }

    with open(save_dir / "evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(eval_record, f, indent=2)

    print(f"Run {run_idx} saved to: {save_dir}")
    return eval_record


def main():
    parser = argparse.ArgumentParser(description="Train XGBoost 5 times on Common Harmonized Dataset")
    parser.add_argument("--runs", type=int, default=5, help="Number of independent training runs")
    parser.add_argument("--n_estimators", type=int, default=120, help="Number of boosting trees")
    parser.add_argument("--max_depth", type=int, default=6, help="Maximum tree depth")
    parser.add_argument("--learning_rate", type=float, default=0.1, help="Learning rate")
    args = parser.parse_args()

    seeds = [42, 101, 777, 1234, 9999]
    if args.runs != len(seeds):
        seeds = [42 + i * 13 for i in range(args.runs)]

    X_train, y_train, X_test, y_test, meta_test = load_common_datasets(DATA_DIR)

    all_results = []
    for idx, seed in enumerate(seeds[:args.runs], 1):
        res = train_single_run(
            run_idx=idx,
            seed=seed,
            X_train=X_train,
            y_train=y_train,
            X_test=X_test,
            y_test=y_test,
            meta_test=meta_test,
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
            learning_rate=args.learning_rate,
        )
        all_results.append(res)

    # Compute Aggregate Stats across the 5 runs
    kdd_accs = [r["kddtest_metrics"]["accuracy"] for r in all_results]
    kdd_f1s = [r["kddtest_metrics"]["f1"] for r in all_results]
    kdd21_accs = [r["kddtest21_metrics"]["accuracy"] for r in all_results]
    kdd21_f1s = [r["kddtest21_metrics"]["f1"] for r in all_results]
    common_accs = [r["common_test_metrics"]["accuracy"] for r in all_results]
    common_f1s = [r["common_test_metrics"]["f1"] for r in all_results]
    unsw_accs = [r["unsw_test_metrics"]["accuracy"] for r in all_results]
    unsw_f1s = [r["unsw_test_metrics"]["f1"] for r in all_results]

    print("\n" + "=" * 65)
    print("ALL 5 RUNS COMPLETED SUCCESSFULLY - SUMMARY STATISTICS")
    print("=" * 65)
    print(f"Overall Common Test Acc: {np.mean(common_accs):.4f} +/- {np.std(common_accs):.4f} | F1: {np.mean(common_f1s):.4f} +/- {np.std(common_f1s):.4f}")
    print(f"KDDTest+ Subset Acc:     {np.mean(kdd_accs):.4f} +/- {np.std(kdd_accs):.4f} | F1: {np.mean(kdd_f1s):.4f} +/- {np.std(kdd_f1s):.4f}")
    print(f"KDDTest-21 Subset Acc:   {np.mean(kdd21_accs):.4f} +/- {np.std(kdd21_accs):.4f} | F1: {np.mean(kdd21_f1s):.4f} +/- {np.std(kdd21_f1s):.4f}")
    print(f"UNSW-NB15 Subset Acc:    {np.mean(unsw_accs):.4f} +/- {np.std(unsw_accs):.4f} | F1: {np.mean(unsw_f1s):.4f} +/- {np.std(unsw_f1s):.4f}")
    print("=" * 65)


if __name__ == "__main__":
    main()

