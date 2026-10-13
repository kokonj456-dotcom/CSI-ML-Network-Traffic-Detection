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
from sklearn.model_selection import train_test_split

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]

DATA_DIR = PROJECT_ROOT / "data-pipeline" / "output" / "NSL-KDD" / "feature_engineered"
MODEL_DIR = AUTOENCODER_DIR
CSV_DIR = MODEL_DIR / "results" / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder

device = torch.device("cpu")
PERCENTILE = 95
TOP_K_VALUES = (3, 5, 10)


def main():
    # Load datasets
    train_x = pd.read_csv(DATA_DIR / "KDDTrain_features.csv")
    train_y = pd.read_csv(DATA_DIR / "KDDTrain_targets.csv")
    test_x = pd.read_csv(DATA_DIR / "KDDTest_features.csv")
    test_y = pd.read_csv(DATA_DIR / "KDDTest_targets.csv")

    with open(MODEL_DIR / "feature_columns.txt", encoding="utf-8") as f:
        feature_columns = [line.strip() for line in f if line.strip()]

    train_x = train_x[feature_columns]
    test_x = test_x[feature_columns]

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    # Recreate Normal Validation split
    normal_mask = train_y["is_attack"].to_numpy() == 0
    _, normal_val = train_test_split(
        train_x.loc[normal_mask],
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    normal_scaled = scaler.transform(normal_val)
    test_scaled = scaler.transform(test_x)

    # Load trained model
    model = Autoencoder(input_dim=len(feature_columns)).to(device)
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location=device,
            weights_only=True,
        )
    )
    model.eval()

    def get_squared_errors(scaled_data: np.ndarray, batch_size=1024) -> np.ndarray:
        batches = []
        with torch.no_grad():
            for start in range(0, len(scaled_data), batch_size):
                batch = torch.as_tensor(
                    scaled_data[start : start + batch_size],
                    dtype=torch.float32,
                    device=device,
                )
                reconstructed = model(batch).cpu().numpy()
                original = scaled_data[start : start + batch_size]
                batches.append(np.square(original - reconstructed))
        return np.concatenate(batches, axis=0)

    print("Computing reconstruction errors...")
    val_errors = get_squared_errors(normal_scaled)
    test_errors = get_squared_errors(test_scaled)

    # Define score functions
    def score_all_mean(errors: np.ndarray) -> np.ndarray:
        return errors.mean(axis=1)

    def score_top_k(errors: np.ndarray, k: int) -> np.ndarray:
        return np.sort(errors, axis=1)[:, -k:].mean(axis=1)

    methods = {"Baseline (MSE all features)": (score_all_mean(val_errors), score_all_mean(test_errors))}
    for k in TOP_K_VALUES:
        methods[f"Top-{k} features"] = (
            score_top_k(val_errors, k),
            score_top_k(test_errors, k),
        )

    # Prepare labels
    y_true = test_y["is_attack"].astype(int).to_numpy()
    test_labels = test_y["label"].astype(str).str.strip().str.lower().to_numpy()
    train_labels = set(
        train_y.loc[train_y["is_attack"] == 1, "label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    summary_rows = []
    family_rows = []

    print(f"\nEvaluating at P{PERCENTILE} threshold:")
    print("=" * 80)

    for method_name, (val_score, test_score) in methods.items():
        threshold = np.percentile(val_score, PERCENTILE)
        predicted = (test_score > threshold).astype(int)

        accuracy = accuracy_score(y_true, predicted)
        precision = precision_score(y_true, predicted, zero_division=0)
        recall = recall_score(y_true, predicted, zero_division=0)
        f1 = f1_score(y_true, predicted, zero_division=0)

        tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
        fpr = fp / (fp + tn) if (fp + tn) else 0.0

        known_mask = (y_true == 1) & np.isin(test_labels, list(train_labels))
        unseen_mask = (y_true == 1) & ~np.isin(test_labels, list(train_labels))

        known_recall = predicted[known_mask].mean() if known_mask.any() else 0.0
        unseen_recall = predicted[unseen_mask].mean() if unseen_mask.any() else 0.0

        summary_rows.append({
            "method": method_name,
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

        print(
            f"{method_name:30s} "
            f"F1={f1:.4f}  "
            f"Acc={accuracy:.4f}  "
            f"Prec={precision:.4f}  "
            f"Rec={recall:.4f}  "
            f"FPR={fpr:.4f}  "
            f"Unseen={unseen_recall:.4f}"
        )

        for label in sorted(set(test_labels[y_true == 1])):
            mask = (y_true == 1) & (test_labels == label)
            total = int(mask.sum())
            detected = int(predicted[mask].sum())

            family_rows.append({
                "method": method_name,
                "attack_label": label,
                "total": total,
                "detected": detected,
                "missed": total - detected,
                "recall": detected / total if total else 0.0,
                "unseen_by_label": label not in train_labels,
            })

    summary_path = CSV_DIR / "topk_scoring_summary.csv"
    family_path = CSV_DIR / "topk_scoring_by_attack.csv"

    pd.DataFrame(summary_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(family_rows).to_csv(family_path, index=False, encoding="utf-8-sig")

    print(f"\nSaved summary: {summary_path}")
    print(f"Saved per-attack details: {family_path}")


if __name__ == "__main__":
    main()
