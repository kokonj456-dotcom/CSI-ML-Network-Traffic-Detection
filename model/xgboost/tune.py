"""
Fine-tuning XGBoost with 5 strategic hyperparameter variations
Evaluates performance on KDDTest+ and KDDTest-21, saves each run to backup,
and reports the best parameter setting.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import json
import pandas as pd

from train import train_and_evaluate, argparse

# Define 5 distinct parameter profiles designed to improve generalization
TUNING_CONFIGS = [
    {
        "name": "Config 1: Conservative & Deep (Lower LR, Deeper Trees, High Estimators)",
        "mode": "binary",
        "n_estimators": 250,
        "max_depth": 8,
        "learning_rate": 0.05,
        "subsample": 0.85,
        "colsample_bytree": 0.70,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "name": "Config 2: High Regularization (Shallow Trees to reduce Overfitting)",
        "mode": "binary",
        "n_estimators": 200,
        "max_depth": 4,
        "learning_rate": 0.08,
        "subsample": 0.75,
        "colsample_bytree": 0.65,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "name": "Config 3: Moderate Depth & Feature Bagging (Balanced Capacity)",
        "mode": "binary",
        "n_estimators": 180,
        "max_depth": 6,
        "learning_rate": 0.06,
        "subsample": 0.80,
        "colsample_bytree": 0.75,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "name": "Config 4: Ultra Subsampling (Diverse Bagging for Novel Attacks)",
        "mode": "binary",
        "n_estimators": 220,
        "max_depth": 7,
        "learning_rate": 0.05,
        "subsample": 0.65,
        "colsample_bytree": 0.60,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "name": "Config 5: Fast Adapted Gradient (Low Depth, Medium LR, High Trees)",
        "mode": "binary",
        "n_estimators": 300,
        "max_depth": 5,
        "learning_rate": 0.04,
        "subsample": 0.80,
        "colsample_bytree": 0.70,
        "cv_folds": 0,
        "random_state": 42
    }
]

def run_tuning():
    results_list = []
    backup_base = Path("model/xgboost/backup")
    backup_base.mkdir(parents=True, exist_ok=True)

    print("================================================================")
    print(" Starting 5 Fine-Tuning Experiments for XGBoost")
    print("================================================================")

    for i, cfg in enumerate(TUNING_CONFIGS, 1):
        print(f"\n>>> Running [{i}/5]: {cfg['name']}")
        iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        run_dir = backup_base / f"xgboost-{iso_str}-tune{i}-binary"
        
        args = argparse.Namespace(
            data_dir="data-pipeline/output/NSL-KDD/feature_engineered",
            backup_dir=str(backup_base),
            mode=cfg["mode"],
            cv_folds=cfg["cv_folds"],
            n_estimators=cfg["n_estimators"],
            max_depth=cfg["max_depth"],
            learning_rate=cfg["learning_rate"],
            subsample=cfg["subsample"],
            colsample_bytree=cfg["colsample_bytree"],
            random_state=cfg["random_state"]
        )

        res, saved_dir = train_and_evaluate(args, save_dir=run_dir)
        m = res["kddtest_metrics"]
        m21 = res["kddtest21_metrics"]

        results_list.append({
            "run": f"Tune {i}",
            "dir": saved_dir.name,
            "params": f"est={cfg['n_estimators']}, depth={cfg['max_depth']}, lr={cfg['learning_rate']}, sub={cfg['subsample']}, col={cfg['colsample_bytree']}",
            "test_acc": m["accuracy"],
            "test_f1": m["macro_f1"],
            "test_recall": m["recall"],
            "test_precision": m["precision"],
            "test21_acc": m21["accuracy"],
            "test21_recall": m21["recall"],
        })

    df = pd.DataFrame(results_list)
    print("\n" + "="*80)
    print(" Fine-Tuning Summary Table")
    print("="*80)
    print(df[["run", "params", "test_acc", "test_f1", "test_recall", "test21_acc"]].to_string(index=False))

    # Identify best
    best_by_f1 = df.sort_values(by="test_f1", ascending=False).iloc[0]
    best_by_recall = df.sort_values(by="test_recall", ascending=False).iloc[0]
    best_by_21 = df.sort_values(by="test21_acc", ascending=False).iloc[0]

    print("\n" + "="*80)
    print(" BEST HYPERPARAMETER SETTINGS:")
    print("="*80)
    print(f"★ Best Overall F1-Score: {best_by_f1['run']} ({best_by_f1['dir']})")
    print(f"  Test Accuracy: {best_by_f1['test_acc']*100:.2f}% | Test F1: {best_by_f1['test_f1']:.4f}")
    print(f"  Params: {best_by_f1['params']}")
    print(f"\n★ Highest Attack Recall: {best_by_recall['run']} ({best_by_recall['dir']})")
    print(f"  Recall on Test: {best_by_recall['test_recall']*100:.2f}% | KDDTest-21 Acc: {best_by_recall['test21_acc']*100:.2f}%")
    print(f"  Params: {best_by_recall['params']}")

if __name__ == "__main__":
    run_tuning()

