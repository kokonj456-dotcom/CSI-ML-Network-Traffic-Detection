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

PERCENTILES = [90, 95]


def main():
    # 1. Load KDDTrain only; do not load KDDTest
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

    # 2. Reproduce the normal validation split used previously
    normal_x = train_x.loc[train_y["is_attack"].eq(0)]

    _, normal_val = train_test_split(
        normal_x,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    # 3. Use KDDTrain attack records for scoring-method development
    attack_val = train_x.loc[train_y["is_attack"].eq(1)]
    attack_labels = (
        train_y.loc[attack_val.index, "label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

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

    val_scores = calculate_scores(normal_val)
    attack_scores = calculate_scores(attack_val)

    # 4. Evaluate each scoring method at P90 and P95
    results = []

    for method, norm_vals in val_scores.items():
        att_vals = attack_scores[method]

        for p in PERCENTILES:
            threshold = float(np.percentile(norm_vals, p))

            fpr = float(np.mean(norm_vals > threshold))
            overall_recall = float(np.mean(att_vals > threshold))

            warez_mask = attack_labels.eq("warezclient").to_numpy()
            warez_recall = (
                float(np.mean(att_vals[warez_mask] > threshold))
                if np.any(warez_mask)
                else 0.0
            )

            results.append({
                "method": method,
                "percentile": f"P{p}",
                "threshold": threshold,
                "val_fpr": fpr,
                "overall_attack_recall": overall_recall,
                "warezclient_recall": warez_recall,
                "val_records": len(norm_vals),
                "attack_records": len(att_vals),
                "warez_records": int(warez_mask.sum()),
            })

    summary = pd.DataFrame(results)

    print("=== Validation Scoring Method Comparison ===")
    print(
        summary[
            [
                "method",
                "percentile",
                "threshold",
                "val_fpr",
                "overall_attack_recall",
                "warezclient_recall",
            ]
        ]
        .round(4)
        .to_string(index=False)
    )

    output = CSV_DIR / "validation_scoring_comparison.csv"
    pd.DataFrame(results).to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\nSaved results: {output}")


if __name__ == "__main__":
    main()
