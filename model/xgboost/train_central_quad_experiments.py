#!/usr/bin/env python3
"""
XGBoost Central Quad-Dataset 4-Model Factorial Experiment Runner
2x2 Factorial Design:
  Factor 1 (Data): Real Traffic (467,860 flows) vs SMOTENC (506,651 flows)
  Factor 2 (Weighting): Natural Empirical Weight vs Balanced Class Weight

Models:
  - Model 1: Real Traffic + Natural Weight (Baseline)
  - Model 2: Real Traffic + Balanced Class Weight
  - Model 3: SMOTENC + Natural Weight
  - Model 4: SMOTENC + Post-SMOTE Balanced Class Weight

All models monitored with Early Stopping (patience=40) against Authentic Real Validation Set (121,199 flows).
Evaluated on Held-Out Authentic Test Benchmark (143,095 flows) across 4 network domains.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    log_loss,
    precision_recall_fscore_support,
)
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "data-pipeline"
FEAT_ENG_DIR = PIPELINE_DIR / "CENTRAL" / "output" / "feature_engineering"
SPLITS_DIR = PIPELINE_DIR / "CENTRAL" / "output" / "splits"
DASHBOARD_DIR = PROJECT_ROOT / "webdashboard" / "xgboost-result"
DASHBOARD_MODELS_DIR = DASHBOARD_DIR / "models"
MODEL_BACKUP_DIR = PROJECT_ROOT / "model" / "xgboost" / "backup"

CLASS_NAMES = [
    "Benign / Normal",
    "Denial of Service (DoS)",
    "Reconnaissance & Probing",
    "Exploits & PrivEsc",
    "Credential Abuse (R2L)",
    "Malware, C2 & Botnet",
]

MITRE_TACTICS = [
    "Baseline Operations",
    "TA0040: Impact",
    "TA0043/TA0007: Recon & Discovery",
    "TA0001/TA0004: Initial Access & PrivEsc",
    "TA0006: Credential Access",
    "TA0011/TA0008: C2 & Lateral Movement",
]

MODEL_PARAMS = {
    "n_estimators": 800,
    "max_depth": 10,
    "learning_rate": 0.03,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "tree_method": "hist",
    "objective": "multi:softprob",
    "num_class": 6,
    "random_state": 42,
    "n_jobs": -1,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 40,
}


def ensure_smote_data() -> Path:
    """Ensure train_smote split exists; generate if missing."""
    smote_dir = SPLITS_DIR / "train_smote"
    feat_file = smote_dir / "features_encoded_19.csv"
    lbl_file = smote_dir / "labels.csv"
    if not (feat_file.exists() and lbl_file.exists()):
        print("train_smote missing; running SMOTENC generation via pipeline_runtime...")
        sys.path.insert(0, str(PIPELINE_DIR))
        from pipeline_runtime import resample
        rep = resample(PIPELINE_DIR / "CENTRAL", split="train", target_class=4, target_samples=40000, random_state=42)
        print("Generated SMOTENC split:", rep)
    return smote_dir


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
    subset_name: str,
) -> dict:
    """Compute comprehensive multiclass and derived binary metrics."""
    acc = accuracy_score(y_true, y_pred)
    bal_acc = balanced_accuracy_score(y_true, y_pred)
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    weighted_p, weighted_r, weighted_f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )
    try:
        loss = log_loss(y_true, y_prob, labels=list(range(6)))
    except Exception:
        loss = None

    prec_arr, rec_arr, f1_arr, supp_arr = precision_recall_fscore_support(
        y_true, y_pred, labels=list(range(6)), zero_division=0
    )

    per_class = []
    for c in range(6):
        per_class.append({
            "class_id": c,
            "class_name": CLASS_NAMES[c],
            "mitre_tactic": MITRE_TACTICS[c],
            "precision": float(round(prec_arr[c] * 100, 2)),
            "recall": float(round(rec_arr[c] * 100, 2)),
            "f1_score": float(round(f1_arr[c] * 100, 2)),
            "support": int(supp_arr[c]),
        })

    cm = confusion_matrix(y_true, y_pred, labels=list(range(6)))
    with np.errstate(divide="ignore", invalid="ignore"):
        cm_norm = np.nan_to_num(cm.astype(float) / cm.sum(axis=1, keepdims=True) * 100)

    # Derived Binary Metrics: 0 = Benign, 1 = Any Attack
    bin_true = (y_true != 0).astype(int)
    bin_pred = (y_pred != 0).astype(int)
    bin_acc = accuracy_score(bin_true, bin_pred)
    bin_p, bin_r, bin_f1, _ = precision_recall_fscore_support(
        bin_true, bin_pred, average="binary", zero_division=0
    )
    bin_cm = confusion_matrix(bin_true, bin_pred, labels=[0, 1])
    far = (bin_cm[0, 1] / bin_cm[0].sum() * 100) if bin_cm[0].sum() > 0 else 0.0

    return {
        "subset_name": subset_name,
        "sample_count": int(len(y_true)),
        "accuracy": float(round(acc * 100, 2)),
        "balanced_accuracy": float(round(bal_acc * 100, 2)),
        "macro_precision": float(round(macro_p * 100, 2)),
        "macro_recall": float(round(macro_r * 100, 2)),
        "macro_f1": float(round(macro_f1 * 100, 2)),
        "weighted_precision": float(round(weighted_p * 100, 2)),
        "weighted_recall": float(round(weighted_r * 100, 2)),
        "weighted_f1": float(round(weighted_f1 * 100, 2)),
        "log_loss": float(round(loss, 4)) if loss is not None else None,
        "binary_accuracy": float(round(bin_acc * 100, 2)),
        "binary_detection_rate": float(round(bin_r * 100, 2)),
        "binary_false_alarm_rate": float(round(far, 2)),
        "binary_precision": float(round(bin_p * 100, 2)),
        "binary_f1": float(round(bin_f1 * 100, 2)),
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
        "confusion_matrix_norm": [[float(round(v, 2)) for v in row] for row in cm_norm],
    }


def get_feature_importances(model, feature_names: list[str]) -> list[dict]:
    """Extract gain and weight scores from XGBoost booster."""
    booster = model.get_booster()
    gain_dict = booster.get_score(importance_type="gain")
    weight_dict = booster.get_score(importance_type="weight")
    total_gain = sum(gain_dict.values()) if gain_dict else 1.0

    records = []
    for i, fname in enumerate(feature_names):
        f_key = f"f{i}"
        gain = gain_dict.get(f_key, 0.0)
        weight = weight_dict.get(f_key, 0.0)
        records.append({
            "feature": fname,
            "gain": float(round(gain, 4)),
            "gain_pct": float(round(gain / total_gain * 100, 2)),
            "weight": int(weight),
        })
    records.sort(key=lambda x: x["gain"], reverse=True)
    return records


def main():
    print("=" * 80)
    print("XGBOOST 4-MODEL FACTORIAL INTRUSION DETECTION BENCHMARK")
    print("2x2 Design: Real vs SMOTE x Natural Weight vs Balanced Class Weight")
    print("=" * 80)

    t_start = time.time()
    DASHBOARD_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load Data
    print("\n[1/5] Loading datasets...")
    # Real Train
    train_dir = FEAT_ENG_DIR / "train"
    print("  Loading Real Train split:", train_dir)
    X_train_df = pd.read_csv(train_dir / "features.csv", low_memory=False)
    y_train_df = pd.read_csv(train_dir / "labels.csv", low_memory=False)
    feature_cols = [c for c in X_train_df.columns if c != "record_id"]
    X_train_real = X_train_df[feature_cols].values.astype(np.float32)
    y_train_real = y_train_df["attack_category_id"].values.astype(int)
    print(f"  Real Train flows ready: {len(X_train_real):,} flows, {len(feature_cols)} features")

    # SMOTE Train
    smote_dir = ensure_smote_data()
    print("  Loading SMOTE Train split:", smote_dir)
    X_smote_df = pd.read_csv(smote_dir / "features_encoded_19.csv", low_memory=False)
    y_smote_df = pd.read_csv(smote_dir / "labels.csv", low_memory=False)
    X_train_smote = X_smote_df[feature_cols].values.astype(np.float32)
    y_train_smote = y_smote_df["attack_category_id"].values.astype(int)
    print(f"  SMOTE Train flows ready: {len(X_train_smote):,} flows")

    # Real Validation (strictly authentic for Early Stopping)
    val_dir = FEAT_ENG_DIR / "validation"
    print("  Loading Authentic Validation split:", val_dir)
    X_val_df = pd.read_csv(val_dir / "features.csv", low_memory=False)
    y_val_df = pd.read_csv(val_dir / "labels.csv", low_memory=False)
    X_val = X_val_df[feature_cols].values.astype(np.float32)
    y_val = y_val_df["attack_category_id"].values.astype(int)
    print(f"  Validation flows ready: {len(X_val):,} flows")

    # Real Test (strictly authentic benchmark)
    test_dir = FEAT_ENG_DIR / "test"
    print("  Loading Authentic Test split:", test_dir)
    X_test_df = pd.read_csv(test_dir / "features.csv", low_memory=False)
    y_test_df = pd.read_csv(test_dir / "labels.csv", low_memory=False)
    meta_test_df = pd.read_csv(test_dir / "metadata.csv", low_memory=False)
    X_test = X_test_df[feature_cols].values.astype(np.float32)
    y_test = y_test_df["attack_category_id"].values.astype(int)
    source_datasets = meta_test_df["source_dataset"].values
    print(f"  Test flows ready: {len(X_test):,} flows")

    # 2. Compute Weights
    weights_real_balanced = compute_sample_weight("balanced", y_train_real)
    weights_smote_balanced = compute_sample_weight("balanced", y_train_smote)

    # 3. Model Training Definitions
    model_configs = [
        {
            "id": "model_1",
            "name": "Model 1: Real Data + Natural Weight",
            "short_name": "M1: Real (Natural)",
            "data_type": "Real",
            "weight_type": "Natural",
            "X": X_train_real,
            "y": y_train_real,
            "weights": None,
            "desc": "Baseline empirical distribution without weighting",
        },
        {
            "id": "model_2",
            "name": "Model 2: Real Data + Balanced Class Weight",
            "short_name": "M2: Real (Balanced)",
            "data_type": "Real",
            "weight_type": "Balanced",
            "X": X_train_real,
            "y": y_train_real,
            "weights": weights_real_balanced,
            "desc": "Real data with inverse class frequency weights",
        },
        {
            "id": "model_3",
            "name": "Model 3: Borderline-SMOTE + Natural Weight",
            "short_name": "M3: SMOTE (Natural)",
            "data_type": "SMOTE",
            "weight_type": "Natural",
            "X": X_train_smote,
            "y": y_train_smote,
            "weights": None,
            "desc": "SMOTENC geometric augmentation with uniform weights",
        },
        {
            "id": "model_4",
            "name": "Model 4: Borderline-SMOTE + Balanced Class Weight",
            "short_name": "M4: SMOTE (Balanced)",
            "data_type": "SMOTE",
            "weight_type": "Balanced",
            "X": X_train_smote,
            "y": y_train_smote,
            "weights": weights_smote_balanced,
            "desc": "SMOTENC augmentation combined with post-SMOTE balanced weights",
        },
    ]

    trained_models = {}
    model_records = {}
    subsets = ["Global Benchmark", "UNSW-NB15", "NSL-KDD", "CIC-IDS2017", "BoT-IoT"]

    for idx, cfg in enumerate(model_configs, start=1):
        m_id = cfg["id"]
        print("\n" + "=" * 80)
        print(f"[{idx+1}/5] Training {cfg['name']} ({len(cfg['X']):,} flows)...")
        print(f"  Configuration: Data={cfg['data_type']} | Weighting={cfg['weight_type']}")
        print(f"  Early stopping on authentic validation set (121,199 flows)...")
        print("=" * 80)

        t0 = time.time()
        clf = XGBClassifier(**MODEL_PARAMS)
        fit_kwargs = {"eval_set": [(X_val, y_val)], "verbose": 100}
        if cfg["weights"] is not None:
            fit_kwargs["sample_weight"] = cfg["weights"]

        clf.fit(cfg["X"], cfg["y"], **fit_kwargs)
        train_time = round(time.time() - t0, 2)
        best_iter = getattr(clf, "best_iteration", MODEL_PARAMS["n_estimators"])
        print(f"Finished in {train_time:.2f}s! Best iteration: {best_iter}")

        # Inferences on Test Set
        print(f"Evaluating {m_id} on Global Test (143,095 flows)...")
        prob_test = clf.predict_proba(X_test)
        pred_test = np.argmax(prob_test, axis=1)

        evals = {}
        for s in subsets:
            mask = np.ones(len(y_test), dtype=bool) if s == "Global Benchmark" else (source_datasets == s)
            evals[s] = evaluate_predictions(y_test[mask], pred_test[mask], prob_test[mask], s)

        feat_imp = get_feature_importances(clf, feature_cols)

        # Print Key Highlights
        glob = evals["Global Benchmark"]
        print(f"  -> Global Acc: {glob['accuracy']}% | Bal Acc: {glob['balanced_accuracy']}% | Macro F1: {glob['macro_f1']}% | Class 4 F1: {glob['per_class'][4]['f1_score']}% (Rec: {glob['per_class'][4]['recall']}%)")

        trained_models[m_id] = clf
        model_records[m_id] = {
            "id": m_id,
            "name": cfg["name"],
            "short_name": cfg["short_name"],
            "data_type": cfg["data_type"],
            "weight_type": cfg["weight_type"],
            "desc": cfg["desc"],
            "train_scale": int(len(cfg["X"])),
            "training_time_seconds": train_time,
            "best_iteration": int(best_iter),
            "evaluations": evals,
            "feature_importance": feat_imp,
        }

        # Save model files
        joblib.dump(clf, DASHBOARD_MODELS_DIR / f"xgboost_{m_id}.joblib")
        joblib.dump(clf, MODEL_BACKUP_DIR / f"xgboost_{m_id}.joblib")
        clf.save_model(str(DASHBOARD_MODELS_DIR / f"xgboost_{m_id}.json"))

    # Compile Final JSON Report
    experiment_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_runtime_seconds": round(time.time() - t_start, 2),
        "dataset_info": {
            "train_real_flows": len(X_train_real),
            "train_smote_flows": len(X_train_smote),
            "validation_flows": len(X_val),
            "test_flows": len(X_test),
            "feature_count": len(feature_cols),
        },
        "hyperparameters": MODEL_PARAMS,
        "features": feature_cols,
        "class_names": CLASS_NAMES,
        "mitre_tactics": MITRE_TACTICS,
        "models": model_records,
        # Backwards compatibility mirrors
        "model_a_baseline": model_records["model_1"],
        "model_b_smote": model_records["model_3"],
    }

    json_out = DASHBOARD_DIR / "experiment_results.json"
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(experiment_payload, f, indent=2)
    print(f"\nAll results exported successfully to: {json_out}")

    # Auto-generate Dashboard HTML
    print("\nGenerating Unified 4-Model Interactive Web Dashboard...")
    gen_script = DASHBOARD_DIR / "generate_html.py"
    if gen_script.exists():
        cmd = [sys.executable, str(gen_script)]
        subprocess.run(cmd, check=True)
        print(f"Dashboard generated at: {DASHBOARD_DIR / 'index.html'}")

    print("\n" + "=" * 80)
    print("ALL 4-MODEL EXPERIMENTS COMPLETED SUCCESSFULLY!")
    print(f"Total time elapsed: {time.time() - t_start:.2f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
