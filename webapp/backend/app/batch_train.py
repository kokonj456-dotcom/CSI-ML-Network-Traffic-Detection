"""
Batch Training Orchestrator: Trains 10 diverse configurations for each model family on the Common Harmonized Dataset.
Families:
  1. XGBoost (10 runs)
  2. MLP (10 runs)
  3. Autoencoder (10 runs)
  4. Isolation Forest (10 runs)
Total: 40 systematic experiment runs with comprehensive metrics, confusion matrices, and parameter logging.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = PROJECT_ROOT / "webapp" / "backend"

CONFIGS = {
    "XGBoost": [
        # Run 1: High Capacity, Standard LR
        {"n_estimators": 150, "max_depth": 7, "learning_rate": 0.1, "subsample": 0.9, "random_state": 42},
        # Run 2: Deeper Trees, Conservative LR
        {"n_estimators": 120, "max_depth": 8, "learning_rate": 0.05, "subsample": 0.85, "random_state": 101},
        # Run 3: Fast Ensemble, Higher LR
        {"n_estimators": 80, "max_depth": 5, "learning_rate": 0.2, "subsample": 0.95, "random_state": 202},
        # Run 4: Regularized Shallow Trees
        {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.08, "subsample": 0.8, "random_state": 303},
        # Run 5: Medium Depth, Balanced Subsample
        {"n_estimators": 100, "max_depth": 6, "learning_rate": 0.12, "subsample": 0.9, "random_state": 404},
        # Run 6: Deep Representation
        {"n_estimators": 140, "max_depth": 9, "learning_rate": 0.04, "subsample": 0.85, "random_state": 505},
        # Run 7: Compact Ultra-fast
        {"n_estimators": 60, "max_depth": 5, "learning_rate": 0.15, "subsample": 0.9, "random_state": 606},
        # Run 8: Extended Boosting
        {"n_estimators": 180, "max_depth": 6, "learning_rate": 0.07, "subsample": 0.88, "random_state": 707},
        # Run 9: Stochastic Aggressive
        {"n_estimators": 110, "max_depth": 7, "learning_rate": 0.14, "subsample": 0.75, "random_state": 808},
        # Run 10: Robust Baseline
        {"n_estimators": 130, "max_depth": 6, "learning_rate": 0.1, "subsample": 0.92, "random_state": 999},
    ],
    "MLP": [
        # Run 1: Wide Layer, Moderate Epochs
        {"epochs": 6, "batch_size": 512, "hidden_dim": 256, "learning_rate": 0.001, "dropout_rate": 0.2, "random_state": 42},
        # Run 2: Compact Layer, Faster Convergence
        {"epochs": 8, "batch_size": 256, "hidden_dim": 128, "learning_rate": 0.0015, "dropout_rate": 0.15, "random_state": 101},
        # Run 3: Deep Capacity, High Regularization
        {"epochs": 10, "batch_size": 512, "hidden_dim": 192, "learning_rate": 0.0008, "dropout_rate": 0.3, "random_state": 202},
        # Run 4: Large Batch, Stable Training
        {"epochs": 8, "batch_size": 1024, "hidden_dim": 256, "learning_rate": 0.002, "dropout_rate": 0.2, "random_state": 303},
        # Run 5: Standard Topology
        {"epochs": 7, "batch_size": 512, "hidden_dim": 128, "learning_rate": 0.001, "dropout_rate": 0.2, "random_state": 404},
        # Run 6: Minimal Dropout
        {"epochs": 6, "batch_size": 512, "hidden_dim": 160, "learning_rate": 0.0012, "dropout_rate": 0.1, "random_state": 505},
        # Run 7: Compact Low Latency
        {"epochs": 9, "batch_size": 256, "hidden_dim": 96, "learning_rate": 0.0015, "dropout_rate": 0.15, "random_state": 606},
        # Run 8: High Epochs, Gentle Decay
        {"epochs": 12, "batch_size": 512, "hidden_dim": 128, "learning_rate": 0.0006, "dropout_rate": 0.25, "random_state": 707},
        # Run 9: Wide Units, High Batch
        {"epochs": 7, "batch_size": 768, "hidden_dim": 224, "learning_rate": 0.0018, "dropout_rate": 0.2, "random_state": 808},
        # Run 10: Balanced Production Baseline
        {"epochs": 8, "batch_size": 512, "hidden_dim": 144, "learning_rate": 0.001, "dropout_rate": 0.2, "random_state": 999},
    ],
    "Autoencoder": [
        # Run 1: 95th Percentile Threshold
        {"epochs": 8, "batch_size": 512, "learning_rate": 0.001, "threshold_percentile": 95.0, "random_state": 42},
        # Run 2: Strict Sensitivity (90th Percentile)
        {"epochs": 8, "batch_size": 512, "learning_rate": 0.001, "threshold_percentile": 90.0, "random_state": 101},
        # Run 3: Conservative Low False Alarm (98th Percentile)
        {"epochs": 10, "batch_size": 512, "learning_rate": 0.0008, "threshold_percentile": 98.0, "random_state": 202},
        # Run 4: Ultra Strict (85th Percentile)
        {"epochs": 6, "batch_size": 256, "learning_rate": 0.0015, "threshold_percentile": 85.0, "random_state": 303},
        # Run 5: High Epoch Reconstruction
        {"epochs": 12, "batch_size": 512, "learning_rate": 0.0007, "threshold_percentile": 95.0, "random_state": 404},
        # Run 6: 92nd Percentile Threshold
        {"epochs": 7, "batch_size": 512, "learning_rate": 0.001, "threshold_percentile": 92.0, "random_state": 505},
        # Run 7: 97th Percentile Threshold
        {"epochs": 9, "batch_size": 512, "learning_rate": 0.0009, "threshold_percentile": 97.0, "random_state": 606},
        # Run 8: Fast Epochs, 94th Percentile
        {"epochs": 5, "batch_size": 256, "learning_rate": 0.002, "threshold_percentile": 94.0, "random_state": 707},
        # Run 9: Large Batch, 96th Percentile
        {"epochs": 10, "batch_size": 1024, "learning_rate": 0.0012, "threshold_percentile": 96.0, "random_state": 808},
        # Run 10: 93rd Percentile Balanced
        {"epochs": 8, "batch_size": 512, "learning_rate": 0.001, "threshold_percentile": 93.0, "random_state": 999},
    ],
    "Isolation Forest": [
        # Run 1: Standard 100 Trees, 15% Contamination
        {"n_estimators": 100, "contamination": 0.15, "random_state": 42},
        # Run 2: High Contamination (20%)
        {"n_estimators": 80, "contamination": 0.20, "random_state": 101},
        # Run 3: Low Contamination (10%)
        {"n_estimators": 120, "contamination": 0.10, "random_state": 202},
        # Run 4: Conservative 8%
        {"n_estimators": 90, "contamination": 0.08, "random_state": 303},
        # Run 5: High Ensemble (150 Trees)
        {"n_estimators": 150, "contamination": 0.15, "random_state": 404},
        # Run 6: Fast Ensemble (60 Trees)
        {"n_estimators": 60, "contamination": 0.18, "random_state": 505},
        # Run 7: 12% Contamination
        {"n_estimators": 110, "contamination": 0.12, "random_state": 606},
        # Run 8: 16% Contamination, 130 Trees
        {"n_estimators": 130, "contamination": 0.16, "random_state": 707},
        # Run 9: Strict 5% Contamination
        {"n_estimators": 100, "contamination": 0.05, "random_state": 808},
        # Run 10: Robust 14% Contamination
        {"n_estimators": 90, "contamination": 0.14, "random_state": 999},
    ],
}


def run_experiment(family: str, idx: int, params: dict):
    param_str = json.dumps(params)
    cmd = [
        sys.executable,
        "-m",
        "app.training_worker",
        "--family",
        family,
        "--dataset",
        "common",
        "--params",
        param_str,
    ]
    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    result = None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if d.get("type") == "result":
                result = d.get("data")
        except Exception:
            pass
    proc.wait()
    elapsed = round(time.time() - t0, 1)

    if proc.returncode != 0:
        err = proc.stderr.read()
        print(f"FAILED [{family} Run {idx+1}]: {err}")
        return False
    else:
        acc = result.get("kddtest_metrics", {}).get("accuracy", 0) if result else 0
        f1 = result.get("kddtest_metrics", {}).get("f1", 0) if result else 0
        print(f"DONE [{family} Run {idx+1}/10 in {elapsed}s] -> Accuracy: {acc*100:.2f}%, F1: {f1:.4f}")
        return True


def main():
    total_start = time.time()
    print("=" * 70)
    print("Starting Systematic Multi-Model Training Studio Benchmark (10 Runs Each)")
    print("Dataset: Common Harmonized (201k train / 104k test)")
    print("=" * 70)

    total_runs = sum(len(cfgs) for cfgs in CONFIGS.values())
    completed = 0

    for family, cfgs in CONFIGS.items():
        print(f"\n--- Training Family: {family} ({len(cfgs)} Variations) ---")
        for i, cfg in enumerate(cfgs):
            success = run_experiment(family, i, cfg)
            if success:
                completed += 1

    total_elapsed = round(time.time() - total_start, 1)
    print("\n" + "=" * 70)
    print(f"All runs completed! {completed}/{total_runs} successful in {total_elapsed}s.")
    print("=" * 70)


if __name__ == "__main__":
    main()

