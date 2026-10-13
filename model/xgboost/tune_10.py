"""
Run 10 fine-tuning attempts across both Binary and Multiclass modes (5 each, 10 total)
Exploring different depths, estimators, learning rates, subsampling, and colsample ratios.
All runs save .joblib models, metrics, and plots into model/xgboost/backup/.
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timezone
import json
import pandas as pd

from train import train_and_evaluate, argparse

TUNING_10_CONFIGS = [
    # --- BINARY ATTEMPTS (5 configs) ---
    {
        "id": "bin-att1",
        "name": "Bin Attempt 1: Deep Regularized (depth 8, subsample 0.60, colsample 0.55)",
        "mode": "binary",
        "n_estimators": 240,
        "max_depth": 8,
        "learning_rate": 0.04,
        "subsample": 0.60,
        "colsample_bytree": 0.55,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "id": "bin-att2",
        "name": "Bin Attempt 2: High Estimators + Low LR (depth 6, lr 0.03, est 350)",
        "mode": "binary",
        "n_estimators": 350,
        "max_depth": 6,
        "learning_rate": 0.03,
        "subsample": 0.70,
        "colsample_bytree": 0.65,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "id": "bin-att3",
        "name": "Bin Attempt 3: Aggressive Feature Bagging (colsample 0.50, sub 0.70)",
        "mode": "binary",
        "n_estimators": 260,
        "max_depth": 7,
        "learning_rate": 0.05,
        "subsample": 0.70,
        "colsample_bytree": 0.50,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "id": "bin-att4",
        "name": "Bin Attempt 4: Compact Forests (depth 5, lr 0.06, est 280, sub 0.65)",
        "mode": "binary",
        "n_estimators": 280,
        "max_depth": 5,
        "learning_rate": 0.06,
        "subsample": 0.65,
        "colsample_bytree": 0.60,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "id": "bin-att5",
        "name": "Bin Attempt 5: Deep Extreme Bagging (depth 9, lr 0.035, sub 0.60, col 0.55)",
        "mode": "binary",
        "n_estimators": 250,
        "max_depth": 9,
        "learning_rate": 0.035,
        "subsample": 0.60,
        "colsample_bytree": 0.55,
        "cv_folds": 0,
        "random_state": 42
    },

    # --- MULTICLASS ATTEMPTS (5 configs) ---
    {
        "id": "multi-att1",
        "name": "Multi Attempt 1: Balanced Grid (depth 6, lr 0.08, est 180, sub 0.75, col 0.70)",
        "mode": "multiclass",
        "n_estimators": 180,
        "max_depth": 6,
        "learning_rate": 0.08,
        "subsample": 0.75,
        "colsample_bytree": 0.70,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "id": "multi-att2",
        "name": "Multi Attempt 2: Diverse Feature Bagging for R2L/U2R (depth 7, col 0.60, sub 0.65)",
        "mode": "multiclass",
        "n_estimators": 220,
        "max_depth": 7,
        "learning_rate": 0.06,
        "subsample": 0.65,
        "colsample_bytree": 0.60,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "id": "multi-att3",
        "name": "Multi Attempt 3: Shallow Trees for DoS/Probe Generalization (depth 5, est 250, lr 0.05)",
        "mode": "multiclass",
        "n_estimators": 250,
        "max_depth": 5,
        "learning_rate": 0.05,
        "subsample": 0.80,
        "colsample_bytree": 0.70,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "id": "multi-att4",
        "name": "Multi Attempt 4: Deep High Capacity (depth 8, est 200, lr 0.05, col 0.65)",
        "mode": "multiclass",
        "n_estimators": 200,
        "max_depth": 8,
        "learning_rate": 0.05,
        "subsample": 0.70,
        "colsample_bytree": 0.65,
        "cv_folds": 0,
        "random_state": 42
    },
    {
        "id": "multi-att5",
        "name": "Multi Attempt 5: Slow Learning Rate Explorer (depth 6, lr 0.04, est 300, sub 0.70)",
        "mode": "multiclass",
        "n_estimators": 300,
        "max_depth": 6,
        "learning_rate": 0.04,
        "subsample": 0.70,
        "colsample_bytree": 0.65,
        "cv_folds": 0,
        "random_state": 42
    }
]

def run_10_tunings():
    results = []
    backup_base = Path("model/xgboost/backup")
    backup_base.mkdir(parents=True, exist_ok=True)

    print("==========================================================================")
    print(" Starting 10 Automated Fine-Tuning Experiments (5 Binary + 5 Multiclass)")
    print("==========================================================================")

    for idx, cfg in enumerate(TUNING_10_CONFIGS, 1):
        print(f"\n>>> [{idx}/10] {cfg['name']}")
        iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        run_dir = backup_base / f"xgboost-{iso_str}-{cfg['id']}-{cfg['mode']}"

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

        results.append({
            "idx": idx,
            "mode": cfg["mode"],
            "id": cfg["id"],
            "dir": saved_dir.name,
            "params": f"est={cfg['n_estimators']}, d={cfg['max_depth']}, lr={cfg['learning_rate']}, sub={cfg['subsample']}, col={cfg['colsample_bytree']}",
            "acc": m["accuracy"],
            "macro_f1": m["macro_f1"],
            "test21_acc": m21["accuracy"],
            "recall": m.get("recall", m.get("macro_recall", 0.0)),
            "precision": m.get("precision", m.get("macro_precision", 0.0))
        })

    df = pd.DataFrame(results)
    print("\n" + "="*95)
    print(" 10 TUNING ATTEMPTS SUMMARY")
    print("="*95)
    print(df[["idx", "mode", "id", "acc", "macro_f1", "test21_acc", "params"]].to_string(index=False))

    print("\n" + "="*95)
    best_bin = df[df["mode"] == "binary"].sort_values(by="macro_f1", ascending=False).iloc[0]
    best_multi = df[df["mode"] == "multiclass"].sort_values(by="macro_f1", ascending=False).iloc[0]

    print(f"🏆 BEST BINARY: {best_bin['id']} ({best_bin['dir']})")
    print(f"   Accuracy: {best_bin['acc']*100:.2f}% | Macro F1: {best_bin['macro_f1']:.4f} | KDDTest-21: {best_bin['test21_acc']*100:.2f}%")
    print(f"   Params: {best_bin['params']}")

    print(f"\n🏆 BEST MULTICLASS: {best_multi['id']} ({best_multi['dir']})")
    print(f"   Accuracy: {best_multi['acc']*100:.2f}% | Macro F1: {best_multi['macro_f1']:.4f} | KDDTest-21: {best_multi['test21_acc']*100:.2f}%")
    print(f"   Params: {best_multi['params']}")

if __name__ == "__main__":
    run_10_tunings()

