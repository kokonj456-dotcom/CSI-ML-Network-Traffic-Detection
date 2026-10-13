import sys
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
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
PNG_DIR = RESULTS_DIR / "png"
CSV_DIR = RESULTS_DIR / "csv"

PNG_DIR.mkdir(parents=True, exist_ok=True)
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder


def get_reconstruction_errors(model, features, scaler, columns):
    scaled = scaler.transform(features[columns])
    tensor = torch.tensor(scaled, dtype=torch.float32)

    model.eval()
    with torch.no_grad():
        reconstructed = model(tensor)
        errors = (
            (tensor - reconstructed) ** 2
        ).mean(dim=1).numpy()

    return errors


def main():
    # 1. โหลดข้อมูล
    train_features = pd.read_csv(
        DATA_DIR / "KDDTrain_features.csv"
    )
    train_targets = pd.read_csv(
        DATA_DIR / "KDDTrain_targets.csv"
    )

    test_features = pd.read_csv(
        DATA_DIR / "KDDTest_features.csv"
    )
    test_targets = pd.read_csv(
        DATA_DIR / "KDDTest_targets.csv"
    )

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    columns = (
        MODEL_DIR / "feature_columns.txt"
    ).read_text(encoding="utf-8").splitlines()

    model = Autoencoder(input_dim=len(columns))
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location="cpu",
            weights_only=True,
        )
    )

    # 2. Normal Validation
    normal_features = train_features.loc[
        train_targets["is_attack"].eq(0)
    ]

    _, X_val = train_test_split(
        normal_features,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    normal_errors = get_reconstruction_errors(
        model, X_val, scaler, columns
    )

    # 3. Reconstruction Error ของ KDDTest
    test_errors = get_reconstruction_errors(
        model, test_features, scaler, columns
    )

    labels = (
        test_targets["label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    attack_mask = test_targets["is_attack"].eq(1)

    known_labels = set(
        train_targets.loc[
            train_targets["is_attack"].eq(1), "label"
        ].astype(str).str.strip().str.lower()
    )

    unseen_mask = attack_mask & ~labels.isin(known_labels)

    # กลุ่มที่ต้องการเปรียบเทียบ
    difficult_labels = [
        "snmpguess",
        "snmpgetattack",
        "mailbomb",
    ]

    easier_labels = [
        "mscan",
        "apache2",
    ]

    difficult_errors = test_errors[
        unseen_mask.to_numpy()
        & labels.isin(difficult_labels).to_numpy()
    ]

    easier_errors = test_errors[
        unseen_mask.to_numpy()
        & labels.isin(easier_labels).to_numpy()
    ]

    # 4. กำหนด Threshold จาก Validation
    threshold = float(np.percentile(normal_errors, 95))

    print("=== Reconstruction Error Summary ===")
    print(f"Normal Validation: {len(normal_errors)} records")
    print(f"Difficult attacks: {len(difficult_errors)} records")
    print(f"Better-detected attacks: {len(easier_errors)} records")
    print(f"P95 Threshold: {threshold:.6f}")

    for name, values in [
        ("Normal Validation", normal_errors),
        ("Difficult Unseen Attacks", difficult_errors),
        ("Better-detected Unseen Attacks", easier_errors),
    ]:
        print(f"\n{name}")
        print(f"Mean:   {np.mean(values):.6f}")
        print(f"Median: {np.median(values):.6f}")
        print(f"Below threshold: {(values <= threshold).mean():.2%}")

    # 5. สร้างกราฟ Histogram
    x_max = 2.0

    plt.figure(figsize=(11, 6))

    plt.hist(
        normal_errors[normal_errors <= x_max],
        bins=60,
        alpha=0.55,
        density=True,
        label="Normal Validation",
    )

    if len(difficult_errors) > 0:
        plt.hist(
            difficult_errors[difficult_errors <= x_max],
            bins=60,
            alpha=0.55,
            density=True,
            label="Difficult Unseen Attacks",
        )

    if len(easier_errors) > 0:
        plt.hist(
            easier_errors[easier_errors <= x_max],
            bins=60,
            alpha=0.55,
            density=True,
            label="Better-detected Unseen Attacks",
        )

    plt.axvline(
        threshold,
        linestyle="--",
        linewidth=2,
        label=f"P95 Threshold = {threshold:.3f}",
    )

    plt.xlabel("Reconstruction Error (MSE)")
    plt.ylabel("Density")
    plt.title("Reconstruction Error Distribution")
    plt.legend()
    plt.tight_layout()

    output_path = PNG_DIR / "reconstruction_error_distribution.png"
    plt.savefig(output_path, dpi=200)
    plt.close()

    print(f"\nGraph saved: {output_path}")


if __name__ == "__main__":
    main()
