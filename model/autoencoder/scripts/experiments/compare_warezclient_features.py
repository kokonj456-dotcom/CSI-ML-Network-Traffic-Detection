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
CSV_DIR = MODEL_DIR / "results" / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder


def main():
    train_x = pd.read_csv(DATA_DIR / "KDDTrain_features.csv")
    train_y = pd.read_csv(DATA_DIR / "KDDTrain_targets.csv")

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    with open(MODEL_DIR / "feature_columns.txt", encoding="utf-8") as f:
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

    normal_x = train_x.loc[train_y["is_attack"].eq(0)]
    _, normal_val = train_test_split(
        normal_x,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    attack_x = train_x.loc[
        train_y["label"].astype(str).str.strip().str.lower()
        .eq("warezclient")
    ]

    def per_feature_errors(df):
        scaled = scaler.transform(df[columns])
        tensor = torch.tensor(scaled, dtype=torch.float32)

        with torch.no_grad():
            reconstructed = model(tensor).numpy()

        return (scaled - reconstructed) ** 2

    normal_errors = per_feature_errors(normal_val)
    attack_errors = per_feature_errors(attack_x)

    norm_mean = normal_errors.mean(axis=0)
    norm_median = np.median(normal_errors, axis=0)
    atk_mean = attack_errors.mean(axis=0)
    atk_median = np.median(attack_errors, axis=0)

    diff_mean = atk_mean - norm_mean
    diff_median = atk_median - norm_median
    ratio_median = atk_median / np.where(norm_median == 0, 1e-9, norm_median)

    result = pd.DataFrame({
        "feature": columns,
        "norm_median": norm_median,
        "attack_median": atk_median,
        "diff_median": diff_median,
        "ratio_median": ratio_median,
        "norm_mean": norm_mean,
        "attack_mean": atk_mean,
        "diff_mean": diff_mean,
    }).sort_values(by="diff_median", ascending=False)

    print("=== Top 15 features with largest median error difference ===")
    print(
        result[
            [
                "feature",
                "norm_median",
                "attack_median",
                "diff_median",
                "ratio_median",
            ]
        ]
        .head(15)
        .round(5)
        .to_string(index=False)
    )

    print("\n=== Top 15 features with largest mean error difference ===")
    print(
        result[
            [
                "feature",
                "norm_mean",
                "attack_mean",
                "diff_mean",
            ]
        ]
        .sort_values(by="diff_mean", ascending=False)
        .head(15)
        .round(5)
        .to_string(index=False)
    )

    output = CSV_DIR / "warezclient_feature_errors.csv"
    result.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\nSaved feature errors to: {output}")


if __name__ == "__main__":
    main()
