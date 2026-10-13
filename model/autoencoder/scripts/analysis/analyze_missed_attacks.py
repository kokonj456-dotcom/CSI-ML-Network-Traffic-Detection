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

DIFFICULT_LABELS = [
    "snmpguess",
    "snmpgetattack",
    "mailbomb",
]


def get_scaled_and_reconstructed(
    model, features, scaler, columns
):
    """ปรับสเกลข้อมูลและให้ Autoencoder สร้างข้อมูลกลับ"""
    scaled = scaler.transform(features[columns])
    tensor = torch.tensor(scaled, dtype=torch.float32)

    model.eval()

    with torch.no_grad():
        reconstructed = model(tensor).cpu().numpy()

    return scaled, reconstructed


def main():
    # 1. โหลดข้อมูลและโมเดล
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

    # คำนวณ Reconstruction Error ของ Normal Validation
    normal_scaled, normal_rec = get_scaled_and_reconstructed(
        model, normal_val, scaler, columns
    )

    normal_errors = np.mean(
        (normal_scaled - normal_rec) ** 2,
        axis=1,
    )

    thresholds = {
        "P90": float(np.percentile(normal_errors, 90)),
        "P95": float(np.percentile(normal_errors, 95)),
    }

    # 3. เตรียม Unseen Difficult Attacks
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

    difficult_mask = (
        is_unseen & test_labels.isin(DIFFICULT_LABELS)
    )

    difficult_x = test_features.loc[difficult_mask].copy()
    difficult_y = test_targets.loc[difficult_mask].copy()

    # 4. คำนวณ Error รายแถวและรายฟีเจอร์ของ Difficult Attacks
    attack_scaled, attack_rec = get_scaled_and_reconstructed(
        model, difficult_x, scaler, columns
    )

    feature_squared_errors = (
        (attack_scaled - attack_rec) ** 2
    )

    record_errors = np.mean(
        feature_squared_errors,
        axis=1,
    )

    # 5. สร้างผลลัพธ์รายแถว
    results = difficult_y.copy()
    results["reconstruction_error"] = record_errors

    for name, value in thresholds.items():
        results[f"missed_{name}"] = record_errors <= value

    # 6. สรุปภาพรวม
    print("=== Difficult Attacks Analysis ===")
    print(f"Total difficult records: {len(results)}")

    for name, value in thresholds.items():
        missed = results[f"missed_{name}"].sum()
        rate = missed / len(results) if len(results) else 0.0

        print(
            f"Missed at {name} ({value:.6f}): "
            f"{missed} records ({rate:.2%})"
        )

    print("\n=== Breakdown by Attack Label ===")

    for label in DIFFICULT_LABELS:
        subset = results[results["label"].str.lower() == label]

        if subset.empty:
            continue

        print(f"\n[{label}] ({len(subset)} records)")
        print(f"Mean error:   {subset['reconstruction_error'].mean():.6f}")
        print(f"Median error: {subset['reconstruction_error'].median():.6f}")

        for name in thresholds:
            missed = subset[f"missed_{name}"].sum()
            rate = missed / len(subset)

            print(f"Missed at {name}: {missed} ({rate:.2%})")

    # 7. วิเคราะห์ฟีเจอร์ที่ Error สูงสุดในกลุ่มที่ตรวจไม่พบ
    summary_rows = []

    for name in thresholds:
        missed_mask = results[f"missed_{name}"].to_numpy()

        if not np.any(missed_mask):
            continue

        missed_feature_errors = feature_squared_errors[
            missed_mask
        ]

        mean_errors = np.mean(
            missed_feature_errors,
            axis=0,
        )

        top_indices = np.argsort(mean_errors)[::-1][:10]

        for rank, idx in enumerate(top_indices, 1):
            summary_rows.append({
                "threshold": name,
                "rank": rank,
                "feature": columns[idx],
                "mean_error": mean_errors[idx],
            })

    summary = pd.DataFrame(summary_rows)

    print("\n=== Top Feature Errors by Threshold ===")

    if not summary.empty:
        print(
            summary.round(5).to_string(index=False)
        )
    else:
        print("No feature error summaries available.")

    # 8. บันทึกผลลัพธ์
    row_output = (
        CSV_DIR / "missed_attack_records_by_threshold.csv"
    )

    feature_output = (
        CSV_DIR
        / "missed_attack_feature_errors_by_threshold.csv"
    )

    results.to_csv(
        row_output,
        index=False,
        encoding="utf-8-sig",
    )

    summary.to_csv(
        feature_output,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"\nSaved records: {row_output}")
    print(f"Saved feature analysis: {feature_output}")


if __name__ == "__main__":
    main()
