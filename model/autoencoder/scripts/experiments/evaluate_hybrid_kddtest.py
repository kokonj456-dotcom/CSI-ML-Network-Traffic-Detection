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

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]

DATA_DIR = PROJECT_ROOT / "data-pipeline" / "output" / "NSL-KDD" / "feature_engineered"
MODEL_DIR = AUTOENCODER_DIR
CSV_DIR = MODEL_DIR / "results" / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder

TRAIN_X_PATH = DATA_DIR / "KDDTrain_features.csv"
TRAIN_Y_PATH = DATA_DIR / "KDDTrain_targets.csv"
TEST_X_PATH = DATA_DIR / "KDDTest_features.csv"
TEST_Y_PATH = DATA_DIR / "KDDTest_targets.csv"

MODEL_PATH = MODEL_DIR / "autoencoder.pth"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
COLUMNS_PATH = MODEL_DIR / "feature_columns.txt"

SELECTED_FEATURES = [
    "dst_host_same_src_port_rate",
    "host_service_rate_gap",
    "dst_host_same_srv_rate",
    "log1p_dst_host_count",
    "dst_host_srv_diff_host_rate",
    "dst_host_count",
    "logged_in",
    "dst_host_diff_srv_rate",
    "log1p_src_bytes",
    "log1p_dst_host_srv_count",
]

ALPHA = 0.25
device = torch.device("cpu")


def main():
    train_X = pd.read_csv(TRAIN_X_PATH)
    train_y = pd.read_csv(TRAIN_Y_PATH)
    test_X = pd.read_csv(TEST_X_PATH)
    test_y = pd.read_csv(TEST_Y_PATH)

    with open(COLUMNS_PATH, "r", encoding="utf-8") as f:
        feature_columns = [line.strip() for line in f if line.strip()]

    selected_features_filtered = [
        name for name in SELECTED_FEATURES if name in feature_columns
    ]

    train_X = train_X[feature_columns]
    test_X = test_X[feature_columns]

    scaler = joblib.load(SCALER_PATH)

    # Feature indices
    selected_indices = [
        feature_columns.index(name) for name in selected_features_filtered
    ]

    # Reproduce Normal Validation split
    normal_mask = train_y["is_attack"] == 0
    from sklearn.model_selection import train_test_split

    X_train_norm, X_val_norm, _, _ = train_test_split(
        train_X[normal_mask],
        train_y[normal_mask],
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    model = Autoencoder(input_dim=len(feature_columns)).to(device)
    model.load_state_dict(
        torch.load(MODEL_PATH, map_location=device, weights_only=True)
    )
    model.eval()

    def get_errors(df, batch_size=1024):
        scaled = scaler.transform(df)
        batches = []
        with torch.no_grad():
            for start in range(0, len(scaled), batch_size):
                batch = torch.as_tensor(
                    scaled[start : start + batch_size],
                    dtype=torch.float32,
                    device=device,
                )
                reconstructed = model(batch).cpu().numpy()
                original = scaled[start : start + batch_size]
                batches.append(np.square(original - reconstructed))
        return np.concatenate(batches, axis=0)

    val_errors = get_errors(X_val_norm)
    test_errors = get_errors(test_X)

    # Scoring methods
    val_base = val_errors.mean(axis=1)
    test_base = test_errors.mean(axis=1)

    val_sel = (
        val_errors[:, selected_indices].mean(axis=1)
        if selected_indices
        else val_base
    )
    test_sel = (
        test_errors[:, selected_indices].mean(axis=1)
        if selected_indices
        else test_base
    )

    # Normalization using Normal Validation parameters
    mean_base = val_base.mean()
    std_base = val_base.std() or 1.0

    mean_sel = val_sel.mean()
    std_sel = val_sel.std() or 1.0

    val_base_std = (val_base - mean_base) / std_base
    test_base_std = (test_base - mean_base) / std_base

    val_sel_std = (val_sel - mean_sel) / std_sel
    test_sel_std = (test_sel - mean_sel) / std_sel

    val_hybrid = (1 - ALPHA) * val_base_std + ALPHA * val_sel_std
    test_hybrid = (1 - ALPHA) * test_base_std + ALPHA * test_sel_std

    methods = {
        "Baseline (all features MSE)": (val_base, test_base),
        "10 Selected Features only": (val_sel, test_sel),
        f"Hybrid (alpha={ALPHA})": (val_hybrid, test_hybrid),
    }

    y_true = test_y["is_attack"].astype(int).to_numpy()
    test_labels = test_y["label"].astype(str).str.strip().str.lower().to_numpy()
    train_labels = (
        train_y.loc[train_y["is_attack"] == 1, "label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )
    known_attack_labels = set(train_labels)

    rows = []
    family_rows = []

    print("=" * 80)
    print("HYBRID SCORING EVALUATION ON KDDTest")
    print("=" * 80)

    for percentile in (90, 95):
        print(f"\n--- Threshold: Normal Validation P{percentile} ---")

        for method_name, (val_score, test_score) in methods.items():
            threshold = float(np.percentile(val_score, percentile))
            predicted = (test_score > threshold).astype(int)

            accuracy = accuracy_score(y_true, predicted)
            precision = precision_score(y_true, predicted, zero_division=0)
            recall = recall_score(y_true, predicted, zero_division=0)
            f1 = f1_score(y_true, predicted, zero_division=0)

            tn, fp, fn, tp = confusion_matrix(
                y_true, predicted, labels=[0, 1]
            ).ravel()
            fpr = fp / (fp + tn) if (fp + tn) else 0.0

            known_mask = (y_true == 1) & np.isin(
                test_labels, list(known_attack_labels)
            )
            unseen_mask = (y_true == 1) & ~np.isin(
                test_labels, list(known_attack_labels)
            )

            known_recall = predicted[known_mask].mean() if known_mask.any() else 0.0
            unseen_recall = (
                predicted[unseen_mask].mean() if unseen_mask.any() else 0.0
            )

            print(
                f"{method_name:30s} "
                f"F1={f1:.4f}  "
                f"Acc={accuracy:.4f}  "
                f"Prec={precision:.4f}  "
                f"Rec={recall:.4f}  "
                f"FPR={fpr:.4f}  "
                f"Known={known_recall:.4f}  "
                f"Unseen={unseen_recall:.4f}"
            )

            rows.append({
                "method": method_name,
                "threshold_percentile": percentile,
                "threshold": threshold,
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "fpr": fpr,
                "tn": tn,
                "fp": fp,
                "fn": fn,
                "tp": tp,
                "known_attack_recall": known_recall,
                "unseen_attack_recall": unseen_recall,
            })

            for label in sorted(set(test_labels[y_true == 1])):
                mask = (y_true == 1) & (test_labels == label)
                total = int(mask.sum())
                detected = int(predicted[mask].sum())

                family_rows.append({
                    "method": method_name,
                    "threshold_percentile": percentile,
                    "attack_label": label,
                    "total": total,
                    "detected": detected,
                    "missed": total - detected,
                    "recall": detected / total if total else 0.0,
                    "unseen_by_label": label not in known_attack_labels,
                })

    summary_path = CSV_DIR / "hybrid_kddtest_summary.csv"
    family_path = CSV_DIR / "hybrid_kddtest_by_attack.csv"

    pd.DataFrame(rows).to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(family_rows).to_csv(family_path, index=False, encoding="utf-8-sig")

    print("\nSaved summary:", summary_path)
    print("Saved per-attack results:", family_path)


if __name__ == "__main__":
    main()
