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
    PROJECT_ROOT / "data-pipeline" / "output"
    / "NSL-KDD" / "feature_engineered"
)
MODEL_DIR = AUTOENCODER_DIR
RESULTS_DIR = MODEL_DIR / "results"
CSV_DIR = RESULTS_DIR / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder

METHODS = ["MSE", "Top5_Mean", "Top10_Mean", "Max_Error"]
PERCENTILES = [90, 95]


def main():
    # Load KDDTrain only; KDDTest is not used here.
    train_x = pd.read_csv(DATA_DIR / "KDDTrain_features.csv")
    train_y = pd.read_csv(DATA_DIR / "KDDTrain_targets.csv")

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    with open(
        MODEL_DIR / "feature_columns.txt",
        encoding="utf-8",
    ) as f:
        columns = [line.strip() for line in f if line.strip()]

    model = Autoencoder(input_dim=len(columns))
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location="cpu",
            weights_only=True,
        )
    )
    model.eval()

    def calculate_scores(df):
        scaled = scaler.transform(df[columns])
        tensor = torch.tensor(scaled, dtype=torch.float32)

        with torch.no_grad():
            reconstructed = model(tensor).numpy()

        errors = (scaled - reconstructed) ** 2

        return {
            "MSE": errors.mean(axis=1),
            "Top5_Mean": np.sort(errors, axis=1)[:, -5:].mean(axis=1),
            "Top10_Mean": np.sort(errors, axis=1)[:, -10:].mean(axis=1),
            "Max_Error": errors.max(axis=1),
        }

    normal_x = train_x.loc[train_y["is_attack"].eq(0)]
    _, normal_val = train_test_split(
        normal_x,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    attack_x = train_x.loc[train_y["is_attack"].eq(1)]
    families = (
        train_y.loc[attack_x.index, "attack_family"]
        .astype(str)
        .str.strip()
    )

    val_scores = calculate_scores(normal_val)
    attack_scores = calculate_scores(attack_x)

    rows = []

    for method in METHODS:
        for p in PERCENTILES:
            threshold = float(np.percentile(val_scores[method], p))

            total_detected = (
                attack_scores[method] > threshold
            ).sum()
            total_recall = total_detected / len(attack_x)

            for family in sorted(families.unique()):
                mask = families.eq(family).to_numpy()
                count = int(mask.sum())
                detected = int(
                    (attack_scores[method][mask] > threshold).sum()
                )
                recall = detected / count if count else 0.0

                rows.append({
                    "method": method,
                    "percentile": f"P{p}",
                    "threshold": threshold,
                    "attack_family": family,
                    "total_attacks": count,
                    "detected": detected,
                    "recall": recall,
                    "overall_train_recall": total_recall,
                })

    result = pd.DataFrame(rows)

    print("=== Training Attack Family Recall by Method ===")

    for p in PERCENTILES:
        print(f"\n--- P{p} Threshold ---")
        pivot = result[result["percentile"] == f"P{p}"].pivot(
            index="attack_family",
            columns="method",
            values="recall",
        )
        print((pivot * 100).round(2).to_string())

        print(
            "\nOverall train recall:",
            result[result["percentile"] == f"P{p}"]
            .drop_duplicates(subset=["method"])[
                ["method", "overall_train_recall"]
            ]
            .set_index("method")
            .to_dict()["overall_train_recall"],
        )

    output = CSV_DIR / "attack_family_recall_train.csv"
    result.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\nSaved results: {output}")


if __name__ == "__main__":
    main()
