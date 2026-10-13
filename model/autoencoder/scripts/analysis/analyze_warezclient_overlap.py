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

    def get_errors(df):
        scaled = scaler.transform(df[columns])
        tensor = torch.tensor(scaled, dtype=torch.float32)

        with torch.no_grad():
            reconstructed = model(tensor).numpy()

        return ((scaled - reconstructed) ** 2).mean(axis=1)

    normal_x = train_x.loc[train_y["is_attack"].eq(0)]
    _, normal_val = train_test_split(
        normal_x,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    warezclient_x = train_x.loc[
        train_y["label"].astype(str).str.strip().str.lower()
        .eq("warezclient")
    ]

    val_errors = get_errors(normal_val)
    warez_errors = get_errors(warezclient_x)

    print("=== Summary statistics ===")
    print(f"Normal Validation records: {len(val_errors)}")
    print(f"  Mean:   {val_errors.mean():.6f}")
    print(f"  Median: {np.median(val_errors):.6f}")
    print(f"  Min:    {val_errors.min():.6f}")
    print(f"  Max:    {val_errors.max():.6f}")

    print(f"\nwarezclient records: {len(warez_errors)}")
    print(f"  Mean:   {warez_errors.mean():.6f}")
    print(f"  Median: {np.median(warez_errors):.6f}")
    print(f"  Min:    {warez_errors.min():.6f}")
    print(f"  Max:    {warez_errors.max():.6f}")

    print("\n=== Quantile comparison ===")
    quantiles = [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    comparison = pd.DataFrame({
        "Quantile": [f"P{int(q * 100)}" for q in quantiles],
        "Normal_Val": np.percentile(val_errors, [q * 100 for q in quantiles]),
        "warezclient": np.percentile(warez_errors, [q * 100 for q in quantiles]),
    })
    print(comparison.round(6).to_string(index=False))

    print("\n=== Recall at Normal Validation thresholds ===")
    for p in (90, 95):
        threshold = np.percentile(val_errors, p)
        detected = (warez_errors > threshold).sum()
        recall = detected / len(warez_errors)
        fpr = (val_errors > threshold).mean()

        print(
            f"P{p} threshold ({threshold:.6f}): "
            f"detected {detected}/{len(warez_errors)} ({recall:.2%}), "
            f"FPR={fpr:.2%}"
        )

    output = CSV_DIR / "warezclient_error_overlap.csv"
    pd.DataFrame({
        "metric": ["mean", "median", "p90", "p95", "min", "max"],
        "normal_val": [
            val_errors.mean(),
            np.median(val_errors),
            np.percentile(val_errors, 90),
            np.percentile(val_errors, 95),
            val_errors.min(),
            val_errors.max(),
        ],
        "warezclient": [
            warez_errors.mean(),
            np.median(warez_errors),
            np.percentile(warez_errors, 90),
            np.percentile(warez_errors, 95),
            warez_errors.min(),
            warez_errors.max(),
        ],
    }).to_csv(output, index=False, encoding="utf-8-sig")

    print(f"\nSaved summary to: {output}")


if __name__ == "__main__":
    main()
