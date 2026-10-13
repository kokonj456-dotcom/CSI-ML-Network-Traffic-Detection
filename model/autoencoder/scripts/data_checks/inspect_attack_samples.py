import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]
DATA = PROJECT_ROOT / "data-pipeline" / "output" / "NSL-KDD" / "feature_engineered"
MODEL_DIR = AUTOENCODER_DIR
CSV_DIR = MODEL_DIR / "results" / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder

LABELS = ["snmpguess", "snmpgetattack", "mailbomb"]


def main():
    train_x = pd.read_csv(DATA / "KDDTrain_features.csv")
    train_y = pd.read_csv(DATA / "KDDTrain_targets.csv")
    test_x = pd.read_csv(DATA / "KDDTest_features.csv")
    test_y = pd.read_csv(DATA / "KDDTest_targets.csv")

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

    normal_scaled = scaler.transform(normal_val[columns])
    normal_tensor = torch.tensor(normal_scaled, dtype=torch.float32)

    with torch.no_grad():
        normal_reconstructed = model(normal_tensor).numpy()

    normal_errors = np.mean(
        (normal_scaled - normal_reconstructed) ** 2, axis=1
    )
    p90 = np.percentile(normal_errors, 90)
    p95 = np.percentile(normal_errors, 95)

    labels = test_y["label"].astype(str).str.strip().str.lower()
    output_rows = []

    for label in LABELS:
        mask = test_y["is_attack"].eq(1) & labels.eq(label)
        original = test_x.loc[mask, columns]

        if original.empty:
            continue

        scaled = scaler.transform(original)
        tensor = torch.tensor(scaled, dtype=torch.float32)

        with torch.no_grad():
            reconstructed = model(tensor).numpy()

        squared_errors = (scaled - reconstructed) ** 2
        total_errors = squared_errors.mean(axis=1)

        # Focus on missed records at P90
        missed_indices = np.where(total_errors <= p90)[0]

        print(f"\n=== {label} ===")
        print(f"Missed at P90: {len(missed_indices)} / {len(total_errors)}")

        # Inspect up to 3 missed samples per attack type
        for idx in missed_indices[:3]:
            top_idx = np.argsort(squared_errors[idx])[::-1][:10]

            print(
                f"\nSample index: {idx} | "
                f"Total error: {total_errors[idx]:.6f}"
            )

            for j in top_idx:
                print(
                    f"  {columns[j]}: "
                    f"scaled={scaled[idx, j]:.4f}, "
                    f"reconstructed={reconstructed[idx, j]:.4f}, "
                    f"squared_error={squared_errors[idx, j]:.4f}"
                )

            output_rows.append({
                "label": label,
                "sample_index": int(idx),
                "total_error": float(total_errors[idx]),
                "threshold_p90": float(p90),
                "threshold_p95": float(p95),
                "top_error_features": ", ".join(
                    columns[j] for j in top_idx
                ),
            })

    output = CSV_DIR / "attack_sample_inspection.csv"
    pd.DataFrame(output_rows).to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
