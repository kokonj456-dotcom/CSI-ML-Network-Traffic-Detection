"""ฝึก Isolation Forest แบบไฟล์เดียว สำหรับผู้เริ่มต้น

ไฟล์นี้ทำเฉพาะการฝึกโมเดล ไม่ได้ทดสอบโมเดล ไม่ได้สร้างคลัสเตอร์
และไม่อ่านไฟล์ targets เพราะ Isolation Forest เป็นการเรียนรู้แบบ unsupervised

ก่อนรัน
1. รัน data-pipeline/sub-dataset/NSL-KDD/cleansing.ipynb
2. รัน data-pipeline/sub-dataset/NSL-KDD/feature_engineering.ipynb
3. ติดตั้ง dependencies: python -m pip install -r model/isolation-forest/requirements.txt
4. จากโฟลเดอร์รากโปรเจกต์ รัน:
   python model/isolation-forest/train_single.py

ผลลัพธ์
- data-pipeline/sub-dataset/NSL-KDD/output/model_runs/isolation_forest_single/isolation_forest_model.joblib
  ตัวโมเดลที่ฝึกเสร็จแล้ว สำหรับนำไปใช้ทำนายกับข้อมูลใหม่ในขั้นตอนถัดไป
- data-pipeline/sub-dataset/NSL-KDD/output/model_runs/isolation_forest_single/training_config.json
  สรุปข้อมูลและพารามิเตอร์ที่ใช้ฝึก เพื่อให้ตรวจสอบหรือทำซ้ำการทดลองได้

หมายเหตุ: ไฟล์ output ถูกตั้งค่าให้ Git ไม่อัปโหลด เพราะเป็นไฟล์ที่สร้างจากการรัน
และอาจมีขนาดใหญ่ ส่วนสคริปต์นี้จะถูกเก็บไว้ใน Git ตามปกติ
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


# ---------------------------------------------------------------------------
# 1) ตำแหน่งไฟล์
# ---------------------------------------------------------------------------
# หาโฟลเดอร์โปรเจกต์จากตำแหน่งของไฟล์นี้ จึงไม่ต้องเขียน path แบบผูกกับ
# คอมพิวเตอร์เครื่องใดเครื่องหนึ่ง เช่น C:\\Users\\ชื่อคน\\Desktop\\...
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_FOLDER = (
    PROJECT_ROOT / "data-pipeline" / "sub-dataset" / "NSL-KDD" / "output" / "feature_engineering"
)
TRAIN_FEATURES_FILE = FEATURE_FOLDER / "KDDTrain_features.csv"
FEATURE_SCHEMA_FILE = FEATURE_FOLDER / "feature_schema.csv"

MODEL_OUTPUT_FOLDER = (
    PROJECT_ROOT / "data-pipeline" / "sub-dataset" / "NSL-KDD" / "output" / "model_runs" / "isolation_forest_single"
)
MODEL_OUTPUT_FILE = MODEL_OUTPUT_FOLDER / "isolation_forest_model.joblib"
CONFIG_OUTPUT_FILE = MODEL_OUTPUT_FOLDER / "training_config.json"


# ---------------------------------------------------------------------------
# 2) ค่าตั้งต้นของการฝึก (ปรับได้)
# ---------------------------------------------------------------------------
# จำนวนต้นไม้ที่ช่วยกันตรวจหาความผิดปกติ: มากขึ้นมักใช้เวลาฝึกมากขึ้น
# แต่ผลการให้คะแนนมักนิ่งขึ้น ค่า 300 เป็นจุดเริ่มต้นที่เหมาะกับการทดลองนี้
NUMBER_OF_TREES = 300

# จำนวนแถวที่สุ่มไปสร้างต้นไม้แต่ละต้น
# "auto" หมายถึงใช้ไม่เกิน 256 แถวต่อต้นตามค่าเริ่มต้นของ scikit-learn
MAX_ROWS_PER_TREE = "auto"

# วิธีตั้งเส้นแบ่งว่าอะไรจะถูกมองว่าเป็น outlier
# "auto" ให้ scikit-learn ใช้เกณฑ์มาตรฐานของ Isolation Forest
# ค่านี้ไม่ใช่สัดส่วนการโจมตี และไม่ได้แปลว่าข้อมูลมีการโจมตีกี่เปอร์เซ็นต์
CONTAMINATION_SETTING = "auto"

# สัดส่วนจำนวนคุณลักษณะที่สุ่มให้ต้นไม้แต่ละต้นใช้; 1.0 คือใช้ได้ครบทุกคอลัมน์
FEATURE_SHARE_PER_TREE = 1.0

# False หมายถึงสุ่มแถวโดยไม่เอาแถวเดิมซ้ำในต้นไม้ต้นเดียวกัน
ALLOW_ROW_SAMPLING_WITH_REPLACEMENT = False

# เลขกำหนดการสุ่ม: ใช้เลขเดิมเพื่อให้การทดลองทำซ้ำได้ใกล้เคียงเดิม
RANDOM_SEED = 42

# -1 หมายถึงให้ใช้ CPU cores ที่มีอยู่ เพื่อช่วยให้ฝึกเร็วขึ้น
CPU_WORKERS = -1

# โปรเจกต์เลือก baseline ที่ประกอบด้วยตัวเลขเดิมและ One-Hot features
# ส่วน engineered features ยังไม่นำมารวม เพื่อให้เทียบ baseline ได้ชัดเจน
FEATURE_KINDS_FOR_TRAINING = {"original_numeric", "one_hot"}


def load_training_features() -> pd.DataFrame:
    """อ่านและตรวจ X สำหรับฝึก โดยไม่เปิดอ่านไฟล์ targets เลย"""
    if not TRAIN_FEATURES_FILE.is_file():
        raise FileNotFoundError(
            f"ไม่พบไฟล์ข้อมูลฝึก: {TRAIN_FEATURES_FILE}\n"
            "โปรดรัน data-pipeline/sub-dataset/NSL-KDD/cleansing.ipynb และ "
            "data-pipeline/sub-dataset/NSL-KDD/feature_engineering.ipynb ก่อน"
        )

    if not FEATURE_SCHEMA_FILE.is_file():
        raise FileNotFoundError(
            f"ไม่พบไฟล์อธิบายคอลัมน์: {FEATURE_SCHEMA_FILE}\n"
            "โปรดรัน data-pipeline/sub-dataset/NSL-KDD/feature_engineering.ipynb ก่อน"
        )

    all_training_features = pd.read_csv(TRAIN_FEATURES_FILE)
    feature_schema = pd.read_csv(FEATURE_SCHEMA_FILE)

    required_schema_columns = {"feature", "kind"}
    if not required_schema_columns.issubset(feature_schema.columns):
        raise ValueError(
            "feature_schema.csv ต้องมีคอลัมน์ชื่อ 'feature' และ 'kind'"
        )

    # เลือกเฉพาะคอลัมน์ที่ระบุว่าเป็นตัวเลขเดิมหรือ One-Hot ใน schema
    # วิธีนี้ไม่ต้องพิมพ์ชื่อ feature จำนวนมากด้วยมือ
    selected_feature_names = feature_schema.loc[
        feature_schema["kind"].isin(FEATURE_KINDS_FOR_TRAINING), "feature"
    ].astype(str).tolist()

    if not selected_feature_names:
        raise ValueError("ไม่พบ feature สำหรับฝึกตามชนิดที่กำหนดไว้")

    missing_feature_names = [
        feature_name
        for feature_name in selected_feature_names
        if feature_name not in all_training_features.columns
    ]
    if missing_feature_names:
        raise ValueError(
            "มีชื่อ feature ใน schema ที่ไม่พบในไฟล์ features: "
            f"{missing_feature_names[:10]}"
        )

    # ตารางนี้คือ X: แต่ละแถวเป็นเหตุการณ์ และแต่ละคอลัมน์เป็นเบาะแสให้โมเดล
    training_features = all_training_features.loc[:, selected_feature_names].copy()

    # Isolation Forest ต้องรับตัวเลขที่สมบูรณ์ ไม่มีช่องว่างหรือ Infinity
    try:
        numeric_values = training_features.to_numpy(dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("พบคอลัมน์ที่ไม่ใช่ตัวเลขใน features สำหรับฝึก") from error

    if not np.isfinite(numeric_values).all():
        raise ValueError(
            "features มีค่าว่าง (NaN) หรือ Infinity; โปรดตรวจผลจาก feature engineering"
        )

    if len(training_features) == 0:
        raise ValueError("ไฟล์ features ไม่มีข้อมูลแม้แต่หนึ่งแถว")

    return training_features


def train_isolation_forest(training_features: pd.DataFrame) -> IsolationForest:
    """สร้างและฝึกโมเดลด้วย X เท่านั้น ไม่มี y หรือ label ในขั้นตอนนี้"""
    isolation_forest_model = IsolationForest(
        n_estimators=NUMBER_OF_TREES,
        max_samples=MAX_ROWS_PER_TREE,
        contamination=CONTAMINATION_SETTING,
        max_features=FEATURE_SHARE_PER_TREE,
        bootstrap=ALLOW_ROW_SAMPLING_WITH_REPLACEMENT,
        random_state=RANDOM_SEED,
        n_jobs=CPU_WORKERS,
    )

    # สังเกตว่า fit รับ training_features อย่างเดียว ไม่มี targets หรือ y
    isolation_forest_model.fit(training_features)
    return isolation_forest_model


def save_model_and_training_notes(
    isolation_forest_model: IsolationForest,
    training_features: pd.DataFrame,
) -> None:
    """บันทึกโมเดลและบันทึกค่าที่ใช้ฝึก เพื่อให้นำกลับมาใช้งาน/ตรวจสอบได้"""
    MODEL_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    joblib.dump(isolation_forest_model, MODEL_OUTPUT_FILE)

    training_notes = {
        "algorithm": "IsolationForest",
        "training_data": TRAIN_FEATURES_FILE.relative_to(PROJECT_ROOT).as_posix(),
        "training_rows": int(len(training_features)),
        "training_feature_count": int(training_features.shape[1]),
        "training_feature_names": training_features.columns.tolist(),
        "targets_used_for_fit": False,
        "parameters": {
            "n_estimators": NUMBER_OF_TREES,
            "max_samples": MAX_ROWS_PER_TREE,
            "contamination": CONTAMINATION_SETTING,
            "max_features": FEATURE_SHARE_PER_TREE,
            "bootstrap": ALLOW_ROW_SAMPLING_WITH_REPLACEMENT,
            "random_state": RANDOM_SEED,
            "n_jobs": CPU_WORKERS,
        },
        "model_file": MODEL_OUTPUT_FILE.relative_to(PROJECT_ROOT).as_posix(),
    }

    with CONFIG_OUTPUT_FILE.open("w", encoding="utf-8") as config_file:
        json.dump(training_notes, config_file, ensure_ascii=False, indent=2)


def main() -> None:
    """ทำงานตามลำดับ: โหลดข้อมูล -> ฝึก -> บันทึกผล"""
    training_features = load_training_features()
    isolation_forest_model = train_isolation_forest(training_features)
    save_model_and_training_notes(isolation_forest_model, training_features)

    print("ฝึก Isolation Forest เสร็จแล้ว")
    print(f"จำนวนแถวที่ใช้ฝึก: {len(training_features):,}")
    print(f"จำนวน features ที่ใช้ฝึก: {training_features.shape[1]:,}")
    print("ไม่ได้ใช้ label, attack_family หรือ is_attack ในการฝึก")
    print(f"ไฟล์โมเดล: {MODEL_OUTPUT_FILE}")
    print(f"บันทึกการตั้งค่า: {CONFIG_OUTPUT_FILE}")
    print("ขั้นตอนนี้ยังไม่ได้ทดสอบโมเดลหรือสร้าง cluster")


if __name__ == "__main__":
    main()
