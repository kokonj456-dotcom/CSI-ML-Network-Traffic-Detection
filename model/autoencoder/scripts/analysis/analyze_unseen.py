import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]

DATA_DIR = (
    PROJECT_ROOT
    / "data-pipeline"
    / "output"
    / "NSL-KDD"
    / "feature_engineered"
)
MODEL_DIR = AUTOENCODER_DIR
RESULTS_DIR = MODEL_DIR / "results"
CSV_DIR = RESULTS_DIR / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder

FOCUS_LABELS = [
    "snmpguess",
    "snmpgetattack",
    "mailbomb",
]


def main():
    # 1. Load dataset
    train_x = pd.read_csv(DATA_DIR / "KDDTrain_features.csv")
    train_y = pd.read_csv(DATA_DIR / "KDDTrain_targets.csv")
    test_x = pd.read_csv(DATA_DIR / "KDDTest_features.csv")
    test_y = pd.read_csv(DATA_DIR / "KDDTest_targets.csv")

    # 2. Load scaler and feature list
    scaler = joblib.load(MODEL_DIR / "scaler.pkl")
    feature_columns = (
        MODEL_DIR / "feature_columns.txt"
    ).read_text(encoding="utf-8").splitlines()

    # 3. Load trained model
    model = Autoencoder(input_dim=len(feature_columns))
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location="cpu",
            weights_only=True,
        )
    )
    model.eval()

    # 4. Recreate normal validation split
    normal_mask = train_y["is_attack"].eq(0)
    normal_x = train_x.loc[normal_mask]

    _, normal_val = train_test_split(
        normal_x,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    normal_scaled = scaler.transform(
        normal_val[feature_columns]
    )
    normal_tensor = torch.tensor(
        normal_scaled, dtype=torch.float32
    )

    with torch.no_grad():
        normal_reconstructed = model(normal_tensor)
        normal_errors = (
            (normal_tensor - normal_reconstructed) ** 2
        ).mean(dim=1).numpy()

    # 5. Calculate thresholds from validation errors
    thresholds = {
        "P90": float(np.percentile(normal_errors, 90)),
        "P95": float(np.percentile(normal_errors, 95)),
    }

    # 6. Calculate test reconstruction errors
    test_scaled = scaler.transform(
        test_x[feature_columns]
    )
    test_tensor = torch.tensor(
        test_scaled, dtype=torch.float32
    )

    with torch.no_grad():
        test_reconstructed = model(test_tensor)
        test_errors = (
            (test_tensor - test_reconstructed) ** 2
        ).mean(dim=1).numpy()

    # 7. Identify unseen attacks
    train_labels = set(
        train_y.loc[
            train_y["is_attack"].eq(1), "label"
        ].astype(str).str.strip().str.lower()
    )

    test_labels = (
        test_y["label"].astype(str).str.strip().str.lower()
    )

    is_attack = test_y["is_attack"].eq(1)
    is_unseen = is_attack & ~test_labels.isin(train_labels)

    rows = []

    for name, threshold in thresholds.items():
        fpr = float(np.mean(normal_errors > threshold))

        # Overall test recall
        test_predicted = test_errors > threshold
        overall_recall = float(
            np.mean(test_predicted[is_attack])
        )
        unseen_recall = float(
            np.mean(test_predicted[is_unseen])
        )

        rows.append({
            "threshold_name": name,
            "threshold_value": threshold,
            "group": "Normal Validation",
            "metric": "False Positive Rate",
            "value": fpr,
            "total_records": len(normal_val),
            "flagged": int((normal_errors > threshold).sum()),
        })

        rows.append({
            "threshold_name": name,
            "threshold_value": threshold,
            "group": "All Test Attacks",
            "metric": "Recall",
            "value": overall_recall,
            "total_records": int(is_attack.sum()),
            "flagged": int(test_predicted[is_attack].sum()),
        })

        rows.append({
            "threshold_name": name,
            "threshold_value": threshold,
            "group": "Unseen Test Attacks",
            "metric": "Recall",
            "value": unseen_recall,
            "total_records": int(is_unseen.sum()),
            "flagged": int(test_predicted[is_unseen].sum()),
        })

        for label in FOCUS_LABELS:
            mask = is_unseen & test_labels.eq(label)
            total = int(mask.sum())
            detected = int(test_predicted[mask].sum())
            recall = detected / total if total else 0.0

            rows.append({
                "threshold_name": name,
                "threshold_value": threshold,
                "group": f"Unseen: {label}",
                "metric": "Recall",
                "value": recall,
                "total_records": total,
                "flagged": detected,
            })

    results = pd.DataFrame(rows)

    print("=== Recall by Threshold ===")
    print(results.to_string(index=False))

    output_path = CSV_DIR / "unseen_recall_by_threshold.csv"
    results.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"\nSaved report: {output_path}")


if __name__ == "__main__":
    main()
