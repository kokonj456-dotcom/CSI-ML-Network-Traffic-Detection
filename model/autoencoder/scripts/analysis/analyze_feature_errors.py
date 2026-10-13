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
PNG_DIR = RESULTS_DIR / "png"
CSV_DIR.mkdir(parents=True, exist_ok=True)
PNG_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder


def reconstruct(model, features, scaler, columns):
    """ปรับสเกลและสร้างข้อมูลกลับด้วย Autoencoder"""
    scaled = scaler.transform(features[columns])
    tensor = torch.tensor(scaled, dtype=torch.float32)

    model.eval()
    with torch.no_grad():
        reconstructed = model(tensor).numpy()

    return scaled, reconstructed


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

    # 2. เตรียม Normal Validation
    normal_features = train_features.loc[
        train_targets["is_attack"].eq(0)
    ]

    _, normal_val = train_test_split(
        normal_features,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    # 3. เตรียม Difficult Unseen Attacks
    train_labels = set(
        train_targets.loc[
            train_targets["is_attack"].eq(1), "label"
        ].astype(str).str.strip().str.lower()
    )

    test_labels = (
        test_targets["label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    is_attack = test_targets["is_attack"].eq(1)
    is_unseen = is_attack & ~test_labels.isin(train_labels)

    difficult_labels = [
        "snmpguess",
        "snmpgetattack",
        "mailbomb",
    ]

    difficult_attacks = test_features.loc[
        is_unseen & test_labels.isin(difficult_labels)
    ]

    print("=== Record Count ===")
    print(f"Normal Validation: {len(normal_val)}")
    print(f"Difficult Attacks: {len(difficult_attacks)}")

    # 4. คำนวณ Reconstruction Error รายฟีเจอร์
    normal_scaled, normal_rec = reconstruct(
        model, normal_val, scaler, columns
    )
    attack_scaled, attack_rec = reconstruct(
        model, difficult_attacks, scaler, columns
    )

    normal_mse = np.mean(
        (normal_scaled - normal_rec) ** 2,
        axis=0,
    )
    attack_mse = np.mean(
        (attack_scaled - attack_rec) ** 2,
        axis=0,
    )

    normal_median_err = np.median(
        (normal_scaled - normal_rec) ** 2,
        axis=0,
    )
    attack_median_err = np.median(
        (attack_scaled - attack_rec) ** 2,
        axis=0,
    )

    # 5. สรุปและเปรียบเทียบ
    results = pd.DataFrame({
        "feature": columns,
        "normal_mse": normal_mse,
        "attack_mse": attack_mse,
        "mse_difference": attack_mse - normal_mse,
        "normal_median": normal_median_err,
        "attack_median": attack_median_err,
        "median_difference": (
            attack_median_err - normal_median_err
        ),
    }).sort_values(
        "mse_difference",
        ascending=False,
    )

    output_path = CSV_DIR / "feature_error_comparison.csv"

    results.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n=== Top 15 Features: Higher Error on Difficult Attacks ===")
    print(results.head(15).round(4).to_string(index=False))

    print("\n=== Top 15 Features: Lower Error on Difficult Attacks ===")
    print(
        results.sort_values("mse_difference")
        .head(15)
        .round(4)
        .to_string(index=False)
    )

    print(f"\nSaved report: {output_path}")


if __name__ == "__main__":
    main()
