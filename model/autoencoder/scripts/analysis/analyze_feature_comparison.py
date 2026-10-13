
"""
analyze_feature_comparison.py

วัตถุประสงค์:
เปรียบเทียบ Reconstruction Error ราย Feature ระหว่าง Normal
กับ Attack แต่ละประเภทที่สนใจ

Attack ที่วิเคราะห์:
- snmpguess
- snmpgetattack
- mailbomb

ผลลัพธ์:
- results/csv/feature_comparison_<attack>.csv
- results/csv/feature_comparison_all_attacks.csv
- results/png/feature_comparison_<attack>.png

หมายเหตุ:
ใช้ Autoencoder และ Scaler ที่ฝึกไว้แล้ว
ไม่มีการฝึกโมเดลใหม่
"""

from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
import torch

from sklearn.model_selection import train_test_split


# =========================================================
# 1. กำหนดตำแหน่งโฟลเดอร์
# =========================================================

# ไฟล์นี้อยู่ใน:
# model/autoencoder/scripts/analysis/
#
# parents[2] = model/autoencoder/
AUTOENCODER_DIR = Path(__file__).resolve().parents[2]

# model/autoencoder/ -> model/ -> project root
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]

DATA_DIR = (
    PROJECT_ROOT
    / "data-pipeline"
    / "output"
    / "NSL-KDD"
    / "feature_engineered"
)

MODEL_DIR = AUTOENCODER_DIR

CSV_DIR = MODEL_DIR / "results" / "csv"
PNG_DIR = MODEL_DIR / "results" / "png"

CSV_DIR.mkdir(parents=True, exist_ok=True)
PNG_DIR.mkdir(parents=True, exist_ok=True)


# เพิ่มตำแหน่งโฟลเดอร์โมเดลเพื่อให้ import ได้
if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder


# =========================================================
# 2. กำหนดประเภท Attack ที่ต้องการวิเคราะห์
# =========================================================

TARGET_LABELS = [
    "snmpguess",
    "snmpgetattack",
    "mailbomb",
]

RANDOM_STATE = 42
VALIDATION_SIZE = 0.20
TOP_N_FEATURES = 10

DEVICE = torch.device("cpu")


# =========================================================
# 3. ฟังก์ชันตรวจสอบไฟล์
# =========================================================

def check_required_files():
    """ตรวจสอบว่าชุดข้อมูลและไฟล์โมเดลมีอยู่จริง"""

    required_files = [
        DATA_DIR / "KDDTrain_features.csv",
        DATA_DIR / "KDDTrain_targets.csv",
        DATA_DIR / "KDDTest_features.csv",
        DATA_DIR / "KDDTest_targets.csv",
        MODEL_DIR / "autoencoder.pth",
        MODEL_DIR / "scaler.pkl",
        MODEL_DIR / "feature_columns.txt",
    ]

    missing_files = [
        path for path in required_files
        if not path.exists()
    ]

    if missing_files:
        message = "\n".join(
            f"- {path}" for path in missing_files
        )

        raise FileNotFoundError(
            "ไม่พบไฟล์ที่จำเป็นต่อการวิเคราะห์:\n"
            f"{message}"
        )


# =========================================================
# 4. โหลดชุดข้อมูล
# =========================================================

def load_dataset(name):
    """โหลด Features และ Targets ของชุดข้อมูล"""

    features_path = DATA_DIR / f"{name}_features.csv"
    targets_path = DATA_DIR / f"{name}_targets.csv"

    features = pd.read_csv(features_path)
    targets = pd.read_csv(targets_path)

    if len(features) != len(targets):
        raise ValueError(
            f"{name}: จำนวนแถว Features "
            f"({len(features)}) ไม่ตรงกับ Targets "
            f"({len(targets)})"
        )

    if "is_attack" not in targets.columns:
        raise ValueError(
            f"{name}_targets.csv ไม่มีคอลัมน์ is_attack"
        )

    return features, targets


def normalize_labels(targets):
    """ปรับรูปแบบชื่อ Label ให้เป็นตัวพิมพ์เล็ก"""

    if "label" not in targets.columns:
        raise ValueError(
            "ไม่พบคอลัมน์ label ในไฟล์ Targets "
            "จึงไม่สามารถแยกประเภท Attack ได้"
        )

    return (
        targets["label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )


# =========================================================
# 5. โหลดโมเดลและ Scaler
# =========================================================

def load_model_and_scaler():
    """โหลดโมเดลที่ฝึกแล้วและ Scaler เดิม"""

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    feature_columns_path = (
        MODEL_DIR / "feature_columns.txt"
    )

    with open(
        feature_columns_path,
        "r",
        encoding="utf-8",
    ) as file:
        feature_columns = [
            line.strip()
            for line in file
            if line.strip()
        ]

    if not feature_columns:
        raise ValueError(
            "feature_columns.txt ไม่มีรายชื่อ Feature"
        )

    model = Autoencoder(
        input_dim=len(feature_columns)
    )

    state_dict = torch.load(
        MODEL_DIR / "autoencoder.pth",
        map_location=DEVICE,
        weights_only=True,
    )

    model.load_state_dict(state_dict)
    model.to(DEVICE)
    model.eval()

    return model, scaler, feature_columns


# =========================================================
# 6. คำนวณ Reconstruction Error ราย Feature
# =========================================================

def calculate_feature_errors(
    df,
    model,
    scaler,
    feature_columns,
):
    """
    คำนวณ Squared Reconstruction Error ราย Feature

    Error = (ค่าหลังปรับสเกล - ค่าที่โมเดลสร้างกลับ)^2

    ใช้ Scaler เดิมที่ fit ระหว่างการฝึก
    ไม่ fit Scaler ใหม่กับชุดทดสอบ
    """

    missing_columns = [
        col for col in feature_columns
        if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "ชุดข้อมูลขาด Feature ที่โมเดลต้องใช้: "
            + ", ".join(missing_columns[:10])
        )

    values = df[feature_columns].to_numpy(
        dtype=np.float32
    )

    if not np.isfinite(values).all():
        raise ValueError(
            "พบค่า NaN หรือ Infinity ใน Features "
            "โปรดตรวจสอบขั้นตอนเตรียมข้อมูล"
        )

    scaled = scaler.transform(values)

    tensor = torch.as_tensor(
        scaled,
        dtype=torch.float32,
        device=DEVICE,
    )

    with torch.no_grad():
        reconstructed = model(tensor).cpu().numpy()

    errors = np.square(scaled - reconstructed)

    return errors


# =========================================================
# 7. เปรียบเทียบ Normal กับ Attack
# =========================================================

def compare_feature_errors(
    normal_errors,
    attack_errors,
    feature_columns,
    attack_label,
):
    """สรุป Mean และ Median Error ของแต่ละ Feature"""

    normal_median = np.median(
        normal_errors,
        axis=0,
    )

    attack_median = np.median(
        attack_errors,
        axis=0,
    )

    normal_mean = np.mean(
        normal_errors,
        axis=0,
    )

    attack_mean = np.mean(
        attack_errors,
        axis=0,
    )

    comparison = pd.DataFrame({
        "attack_type": attack_label,
        "feature": feature_columns,
        "normal_count": len(normal_errors),
        "attack_count": len(attack_errors),
        "normal_median_error": normal_median,
        "attack_median_error": attack_median,
        "normal_mean_error": normal_mean,
        "attack_mean_error": attack_mean,
    })

    comparison["median_error_difference"] = (
        comparison["attack_median_error"]
        - comparison["normal_median_error"]
    )

    comparison["mean_error_difference"] = (
        comparison["attack_mean_error"]
        - comparison["normal_mean_error"]
    )

    comparison["median_error_ratio"] = (
        comparison["attack_median_error"]
        / np.maximum(
            comparison["normal_median_error"],
            1e-12,
        )
    )

    comparison["attack_median_higher"] = (
        comparison["median_error_difference"] > 0
    )

    comparison = comparison.sort_values(
        "median_error_difference",
        ascending=False,
    ).reset_index(drop=True)

    return comparison


# =========================================================
# 8. สร้างกราฟเปรียบเทียบ Feature
# =========================================================

def save_comparison_plot(
    comparison,
    attack_label,
):
    """
    สร้างกราฟแท่งเปรียบเทียบ Median Reconstruction Error
    ระหว่าง Normal กับ Attack สำหรับ Feature ที่แตกต่างกันมาก
    """

    try:
        import matplotlib

        matplotlib.use("Agg")

        import matplotlib.pyplot as plt

    except ImportError:
        print(
            "\n[คำเตือน] ไม่พบ matplotlib "
            "จึงข้ามการสร้างกราฟ"
        )
        print(
            "ติดตั้งด้วยคำสั่ง: "
            "python -m pip install matplotlib"
        )
        return

    # เลือก Feature ที่มีความแตกต่างมากที่สุด
    top_features = (
        comparison
        .assign(
            absolute_difference=lambda df:
            df["median_error_difference"].abs()
        )
        .nlargest(TOP_N_FEATURES, "absolute_difference")
        .sort_values("median_error_difference")
    )

    if top_features.empty:
        return

    labels = top_features["feature"].tolist()
    y = np.arange(len(labels))

    normal_values = (
        top_features["normal_median_error"].to_numpy()
    )

    attack_values = (
        top_features["attack_median_error"].to_numpy()
    )

    fig, ax = plt.subplots(
        figsize=(12, max(6, len(labels) * 0.55))
    )

    height = 0.36

    ax.barh(
        y - height / 2,
        normal_values,
        height,
        label="Normal",
    )

    ax.barh(
        y + height / 2,
        attack_values,
        height,
        label=attack_label,
    )

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Median Squared Reconstruction Error")
    ax.set_title(
        f"Normal vs {attack_label}: Top Feature Errors"
    )

    ax.legend()
    ax.grid(axis="x", linestyle="--", alpha=0.3)

    fig.tight_layout()

    output_path = (
        PNG_DIR
        / f"feature_comparison_{attack_label}.png"
    )

    fig.savefig(
        output_path,
        dpi=160,
        bbox_inches="tight",
    )

    plt.close(fig)

    print(f"บันทึกกราฟ: {output_path}")


# =========================================================
# 9. เริ่มการวิเคราะห์
# =========================================================

def main():
    print("=" * 70)
    print("FEATURE RECONSTRUCTION ERROR COMPARISON")
    print("=" * 70)

    check_required_files()

    print(f"\nProject root: {PROJECT_ROOT}")
    print(f"Model directory: {MODEL_DIR}")
    print(f"Data directory: {DATA_DIR}")

    # โหลดข้อมูล
    train_x, train_y = load_dataset("KDDTrain")
    test_x, test_y = load_dataset("KDDTest")

    print("\n=== Dataset Summary ===")
    print(f"KDDTrain: {len(train_x):,} records")
    print(f"KDDTest:  {len(test_x):,} records")

    # โหลดโมเดล
    model, scaler, feature_columns = (
        load_model_and_scaler()
    )

    print(f"Features used by model: {len(feature_columns)}")

    # เลือก Normal จาก KDDTrain
    normal_mask = train_y["is_attack"].eq(0)
    normal_x = train_x.loc[normal_mask].copy()

    if len(normal_x) < 2:
        raise ValueError(
            "ข้อมูล Normal ใน KDDTrain ไม่เพียงพอ "
            "สำหรับแบ่ง Validation"
        )

    # ใช้ Validation subset ตามแนวทางเดิม
    _, normal_val = train_test_split(
        normal_x,
        test_size=VALIDATION_SIZE,
        random_state=RANDOM_STATE,
        shuffle=True,
    )

    print(
        f"\nNormal validation records: "
        f"{len(normal_val):,}"
    )

    # คำนวณ Error ของ Normal
    normal_errors = calculate_feature_errors(
        normal_val,
        model,
        scaler,
        feature_columns,
    )

    test_labels = normalize_labels(test_y)

    all_comparisons = []

    # วิเคราะห์ Attack แต่ละประเภท
    for attack_label in TARGET_LABELS:
        print("\n" + "=" * 70)
        print(f"Attack type: {attack_label}")
        print("=" * 70)

        attack_mask = (
            test_y["is_attack"].eq(1)
            & test_labels.eq(attack_label)
        )

        attack_x = test_x.loc[attack_mask].copy()

        if attack_x.empty:
            print(
                f"ไม่พบข้อมูล Attack ประเภท {attack_label} "
                "ใน KDDTest — ข้ามประเภทนี้"
            )
            continue

        # คำนวณ Reconstruction Error
        attack_errors = calculate_feature_errors(
            attack_x,
            model,
            scaler,
            feature_columns,
        )

        # เปรียบเทียบราย Feature
        comparison = compare_feature_errors(
            normal_errors=normal_errors,
            attack_errors=attack_errors,
            feature_columns=feature_columns,
            attack_label=attack_label,
        )

        # บันทึกผล CSV แยกตามประเภท Attack
        output_csv = (
            CSV_DIR
            / f"feature_comparison_{attack_label}.csv"
        )

        comparison.to_csv(
            output_csv,
            index=False,
            encoding="utf-8-sig",
        )

        all_comparisons.append(comparison)

        print(f"จำนวน Normal: {len(normal_val):,}")
        print(f"จำนวน Attack: {len(attack_x):,}")

        print(
            "\nTop Features ที่ Median Error "
            "ของ Attack สูงกว่า Normal:"
        )

        positive_difference = comparison[
            comparison["median_error_difference"] > 0
        ].head(TOP_N_FEATURES)

        if positive_difference.empty:
            print(
                "ไม่มี Feature ที่ Median Error "
                "ของ Attack สูงกว่า Normal"
            )
        else:
            columns_to_show = [
                "feature",
                "normal_median_error",
                "attack_median_error",
                "median_error_difference",
            ]

            print(
                positive_difference[
                    columns_to_show
                ].to_string(index=False)
            )

        print(f"\nบันทึก CSV: {output_csv}")

        # สร้างกราฟ
        save_comparison_plot(
            comparison,
            attack_label,
        )

    # รวมผลทุก Attack เป็นไฟล์เดียว
    if all_comparisons:
        combined = pd.concat(
            all_comparisons,
            ignore_index=True,
        )

        combined_path = (
            CSV_DIR / "feature_comparison_all_attacks.csv"
        )

        combined.to_csv(
            combined_path,
            index=False,
            encoding="utf-8-sig",
        )

        print("\n" + "=" * 70)
        print("สรุปการวิเคราะห์")
        print("=" * 70)
        print(
            f"จำนวน Attack types ที่วิเคราะห์สำเร็จ: "
            f"{len(all_comparisons)}"
        )
        print(
            f"จำนวนแถวผลลัพธ์รวม: {len(combined):,}"
        )
        print(f"ไฟล์ผลลัพธ์รวม: {combined_path}")

    else:
        print(
            "\nไม่มีผลลัพธ์ที่บันทึกได้ "
            "โปรดตรวจสอบชื่อ Label ใน KDDTest_targets.csv"
        )

    print("\nวิเคราะห์เสร็จแล้ว")


if __name__ == "__main__":
    main()
