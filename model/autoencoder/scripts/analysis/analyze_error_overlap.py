
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

# ตำแหน่งไฟล์โมเดล
MODEL_DIR = AUTOENCODER_DIR


# ============================================================
# 2. นำเข้า Autoencoder model
# ============================================================

if str(AUTOENCODER_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOENCODER_DIR))

from autoencoder_model import Autoencoder


# ============================================================
# 3. กำหนดประเภท Attack ที่ต้องการวิเคราะห์
# ============================================================

LABELS = ["snmpguess", "snmpgetattack", "mailbomb"]


# ============================================================
# 4. คำนวณ Reconstruction Error
# ============================================================

def reconstruction_errors(model, data, scaler, columns):
    scaled = scaler.transform(data[columns])
    tensor = torch.tensor(scaled, dtype=torch.float32)

    with torch.no_grad():
        reconstructed = model(tensor).cpu().numpy()

    return np.mean((scaled - reconstructed) ** 2, axis=1)


# ============================================================
# 5. แสดงรายละเอียดการกระจายของ Error
# ============================================================

def describe_errors(name, errors, threshold):
    errors = np.asarray(errors)

    print(f"\n{name} (n={len(errors)})")
    print(f"  Mean:   {np.mean(errors):.6f}")
    print(f"  Median: {np.median(errors):.6f}")
    print(f"  P25:    {np.percentile(errors, 25):.6f}")
    print(f"  P75:    {np.percentile(errors, 75):.6f}")
    print(f"  P90:    {np.percentile(errors, 90):.6f}")
    print(f"  P95:    {np.percentile(errors, 95):.6f}")
    print(f"  P99:    {np.percentile(errors, 99):.6f}")
    print(
        f"  Above P90 threshold: "
        f"{(errors > threshold).mean():.4%}"
    )


# ============================================================
# 6. ประมวลผลและวิเคราะห์ข้อมูล
# ============================================================

def main():
    # --------------------------------------------------------
    # 6.1 โหลด Dataset
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
    # 6.2 โหลด Scaler และรายชื่อ Features
    # --------------------------------------------------------

    scaler = joblib.load(
        MODEL_DIR / "scaler.pkl"
    )

    columns = (
        MODEL_DIR / "feature_columns.txt"
    ).read_text(encoding="utf-8").splitlines()

    # --------------------------------------------------------
    # 6.3 โหลด Autoencoder
    # --------------------------------------------------------

    model = Autoencoder(input_dim=len(columns))

    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location="cpu",
            weights_only=True,
        )
    )

    model.eval()

    # --------------------------------------------------------
    # 6.4 คำนวณ Error ของ Normal Validation Set
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

    normal_errors = reconstruction_errors(
        model,
        normal_val,
        scaler,
        columns,
    )

    p90 = float(
        np.percentile(normal_errors, 90)
    )

    p95 = float(
        np.percentile(normal_errors, 95)
    )

    # --------------------------------------------------------
    # 6.5 ระบุ Attack ที่ไม่พบในชุด Train
    # --------------------------------------------------------

    train_labels = (
        train_y["label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    test_labels = (
        test_y["label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    known_labels = set(
        train_labels[
            train_y["is_attack"].eq(1)
        ]
    )

    unseen_mask = (
        test_y["is_attack"].eq(1)
        & ~test_labels.isin(known_labels)
    )

    # --------------------------------------------------------
    # 6.6 แสดง Reconstruction Error Distribution
    # --------------------------------------------------------

    print("=== Reconstruction Error Distribution ===")
    print(f"P90 threshold: {p90:.6f}")
    print(f"P95 threshold: {p95:.6f}")

    describe_errors(
        "Normal validation",
        normal_errors,
        p90,
    )

    # --------------------------------------------------------
    # 6.7 วิเคราะห์ Attack แต่ละประเภท
    # --------------------------------------------------------

    rows = []

    for label in LABELS:
        mask = (
            unseen_mask
            & test_labels.eq(label)
        )

        attack_x = test_x.loc[mask]

        errors = reconstruction_errors(
            model,
            attack_x,
            scaler,
            columns,
        )

        describe_errors(
            label,
            errors,
            p90,
        )

        rows.append({
            "label": label,
            "records": len(errors),
            "median_error": np.median(errors),
            "P90_error": np.percentile(errors, 90),
            "P95_error": np.percentile(errors, 95),
            "detected_at_P90": int(
                (errors > p90).sum()
            ),
            "missed_at_P90": int(
                (errors <= p90).sum()
            ),
            "detected_at_P95": int(
                (errors > p95).sum()
            ),
            "missed_at_P95": int(
                (errors <= p95).sum()
            ),
        })

    # --------------------------------------------------------
    # 6.8 บันทึกผลลัพธ์
    # --------------------------------------------------------

    output = pd.DataFrame(rows)

    output_path = (
        MODEL_DIR
        / "results"
        / "csv"
        / "error_overlap_summary.csv"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n=== Summary ===")
    print(output.round(4).to_string(index=False))
    print(f"\nSaved report: {output_path}")


if __name__ == "__main__":
    main()
