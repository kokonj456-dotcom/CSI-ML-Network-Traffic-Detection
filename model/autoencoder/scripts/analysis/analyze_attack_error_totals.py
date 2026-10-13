
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
import torch

from sklearn.model_selection import train_test_split


# ============================================================
# 1. กำหนด Path ของโปรเจกต์
# ============================================================

# ตำแหน่งโฟลเดอร์ model/autoencoder/
AUTOENCODER_DIR = Path(__file__).resolve().parents[2]

# ตำแหน่งโฟลเดอร์หลักของโปรเจกต์
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]

# ตำแหน่ง Dataset
DATA_DIR = (
    PROJECT_ROOT
    / "data-pipeline"
    / "output"
    / "NSL-KDD"
    / "feature_engineered"
)

# ตำแหน่งไฟล์โมเดลและไฟล์ประกอบ
MODEL_DIR = AUTOENCODER_DIR
MODEL_PATH = MODEL_DIR / "autoencoder.pth"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
FEATURE_COLUMNS_PATH = MODEL_DIR / "feature_columns.txt"

# ตำแหน่งบันทึกผลลัพธ์
OUTPUT_PATH = (
    MODEL_DIR
    / "results"
    / "csv"
    / "attack_error_totals.csv"
)


# ============================================================
# 2. นำเข้า Autoencoder model
# ============================================================

# เพิ่มโฟลเดอร์ autoencoder เข้า Python import path
if str(AUTOENCODER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOENCODER_DIR))

from autoencoder_model import Autoencoder


# ============================================================
# 3. กำหนดประเภท Attack ที่ต้องการวิเคราะห์
# ============================================================

LABELS = [
    "snmpguess",
    "snmpgetattack",
    "mailbomb",
]


# ============================================================
# 4. วิเคราะห์ Reconstruction Error
# ============================================================

def main():

    print("=" * 60)
    print("Analyze Attack Reconstruction Errors")
    print("=" * 60)

    print(f"Project root : {PROJECT_ROOT}")
    print(f"Dataset      : {DATA_DIR}")
    print(f"Model        : {MODEL_PATH}")
    print()

    # --------------------------------------------------------
    # 4.1 โหลด Dataset
    # --------------------------------------------------------

    train_x = pd.read_csv(
        DATA_DIR / "KDDTrain_features.csv"
    )

    train_y = pd.read_csv(
        DATA_DIR / "KDDTrain_targets.csv"
    )

    test_x = pd.read_csv(
        DATA_DIR / "KDDTest_features.csv"
    )

    test_y = pd.read_csv(
        DATA_DIR / "KDDTest_targets.csv"
    )

    # --------------------------------------------------------
    # 4.2 โหลด Scaler และรายชื่อ Features
    # --------------------------------------------------------

    scaler = joblib.load(SCALER_PATH)

    with open(
        FEATURE_COLUMNS_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        columns = [
            line.strip()
            for line in file
            if line.strip()
        ]

    # --------------------------------------------------------
    # 4.3 โหลด Autoencoder ที่เทรนไว้แล้ว
    # --------------------------------------------------------

    model = Autoencoder(input_dim=len(columns))

    state_dict = torch.load(
        MODEL_PATH,
        map_location="cpu",
        weights_only=True,
    )

    model.load_state_dict(state_dict)
    model.eval()

    print(f"จำนวน Features: {len(columns)}")
    print(f"Train records : {len(train_x):,}")
    print(f"Test records  : {len(test_x):,}")

    # --------------------------------------------------------
    # 4.4 ฟังก์ชันคำนวณ Reconstruction Error
    # --------------------------------------------------------

    def errors(df):

        if df.empty:
            return np.array([], dtype=np.float64)

        values = df[columns].to_numpy(
            dtype=np.float32
        )

        # ใช้ Scaler ที่บันทึกไว้จากขั้นตอน Training
        scaled = scaler.transform(values)

        tensor = torch.tensor(
            scaled,
            dtype=torch.float32,
        )

        with torch.no_grad():
            reconstructed = model(tensor).cpu().numpy()

        # คำนวณ Squared Error ของแต่ละ Feature
        per_feature = (scaled - reconstructed) ** 2

        # Mean Squared Reconstruction Error ต่อหนึ่งแถว
        total = per_feature.mean(axis=1)

        return total

    # --------------------------------------------------------
    # 4.5 สร้าง Normal Validation Set
    # --------------------------------------------------------

    normal_x = train_x.loc[
        train_y["is_attack"].eq(0)
    ]

    _, normal_val = train_test_split(
        normal_x,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    normal_errors = errors(normal_val)

    # ใช้ Percentile ของ Normal Error เป็น Threshold
    p90 = np.percentile(normal_errors, 90)
    p95 = np.percentile(normal_errors, 95)

    print("\n=== Normal Validation Threshold ===")
    print(f"Threshold P90: {p90:.6f}")
    print(f"Threshold P95: {p95:.6f}")

    # --------------------------------------------------------
    # 4.6 วิเคราะห์ Attack แต่ละประเภทใน KDDTest
    # --------------------------------------------------------

    labels = (
        test_y["label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    results = []

    for label in LABELS:

        mask = (
            test_y["is_attack"].eq(1)
            & labels.eq(label)
        )

        attack_x = test_x.loc[mask]
        attack_errors = errors(attack_x)

        if len(attack_errors) == 0:
            print(
                f"\nข้าม {label}: "
                "ไม่พบข้อมูล Attack ประเภทนี้"
            )
            continue

        detected_p90 = int(
            (attack_errors > p90).sum()
        )

        detected_p95 = int(
            (attack_errors > p95).sum()
        )

        print(f"\n=== {label} (n={len(attack_errors)}) ===")
        print(f"Mean:   {attack_errors.mean():.6f}")
        print(f"Median: {np.median(attack_errors):.6f}")
        print(f"P90:    {np.percentile(attack_errors, 90):.6f}")
        print(f"P95:    {np.percentile(attack_errors, 95):.6f}")
        print(f"P99:    {np.percentile(attack_errors, 99):.6f}")

        print(
            f"Detected at P90: "
            f"{detected_p90}/{len(attack_errors)}"
        )

        print(
            f"Detected at P95: "
            f"{detected_p95}/{len(attack_errors)}"
        )

        results.append({
            "label": label,
            "records": len(attack_errors),
            "mean_error": attack_errors.mean(),
            "median_error": np.median(attack_errors),
            "p90_error": np.percentile(
                attack_errors, 90
            ),
            "p95_error": np.percentile(
                attack_errors, 95
            ),
            "p99_error": np.percentile(
                attack_errors, 99
            ),
            "detected_p90": detected_p90,
            "detected_p95": detected_p95,
        })

    # --------------------------------------------------------
    # 4.7 บันทึกผลลัพธ์เป็น CSV
    # --------------------------------------------------------

    if not results:
        print(
            "\nไม่พบผลลัพธ์สำหรับ Attack "
            "ที่ระบุไว้ จึงไม่มีการบันทึก CSV"
        )
        return

    results_df = pd.DataFrame(results)

    # สร้างโฟลเดอร์ results/csv หากยังไม่มี
    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    results_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 60)
    print("Analysis completed")
    print("=" * 60)
    print(f"บันทึกผลลัพธ์ที่: {OUTPUT_PATH}")

    print("\nสรุปผล:")
    print(results_df.to_string(index=False))


if __name__ == "__main__":
    main()
