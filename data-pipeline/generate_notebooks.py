#!/usr/bin/env python3
"""
Notebook Generator for CIC-IDS2017, BoT-IoT, and CENTRAL
Generates comprehensive Jupyter Notebooks matching the structure and style
of NSL-KDD and UNSW-NB15 pipelines.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def make_notebook(cells):
    return {
        "cells": cells,
        "metadata": {
            "language_info": {"name": "python", "version": "3.10.19"},
            "orig_nbformat": 4
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }

def md_cell(source):
    if isinstance(source, list):
        return {"cell_type": "markdown", "metadata": {}, "source": source}
    return {"cell_type": "markdown", "metadata": {}, "source": [line + "\n" for line in source.strip().split("\n")]}

def code_cell(source):
    if isinstance(source, list):
        return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source}
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [line + "\n" for line in source.strip().split("\n")]}

def generate_cic_notebooks():
    cic_dir = PROJECT_ROOT / "data-pipeline" / "CIC-IDS2017"
    
    # 1. cleansing.ipynb
    cleansing_cells = [
        md_cell("""# ทำความสะอาดข้อมูล CIC-IDS2017 (Data Cleansing)

Notebook นี้เตรียมไฟล์ดิบ `CIC_IDS2017_training-set.csv` และ `CIC_IDS2017_testing-set.csv` 
ให้มีรูปแบบที่ถูกต้อง ตรวจสอบค่าผิดปกติ (Sentinels, Inf, NaN) และขจัดแถวซ้ำซ้อน ก่อนนำเข้าสู่ขั้นตอน Feature Engineering"""),
        md_cell("""## 1. ตรวจสอบพาธและลายนิ้วมือดิจิทัล (SHA-256 Checksum)"""),
        code_cell("""from pathlib import Path
import pandas as pd
import hashlib

raw_dir = Path("raw")
clean_dir = Path("output/cleansing")
clean_dir.mkdir(parents=True, exist_ok=True)

for p in sorted(raw_dir.glob("*.csv")):
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    print(f"File: {p.name:<32} | Size: {p.stat().st_size:>10,} bytes | SHA-256: {h[:16]}...")"""),
        md_cell("""## 2. อ่านรายงานการทำความสะอาดและตรวจสอบ Sentinel Values"""),
        code_cell("""audit_df = pd.read_csv(clean_dir / "cleansing_audit.csv")
display(audit_df)"""),
        md_cell("""## 3. ตรวจสอบความถูกต้องของตาราง Cleansed และการกระจายตัวของ Label"""),
        code_cell("""train_clean = pd.read_csv(clean_dir / "CIC_IDS2017_training-set.csv")
print(f"CIC-IDS2017 Training Set Shape: {train_clean.shape}")
print("\\nLabel Distribution in Cleansed Training Set:")
print(train_clean["label"].value_counts())""")
    ]
    with open(cic_dir / "cleansing.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(cleansing_cells), f, indent=1)

    # 2. eda.ipynb
    eda_cells = [
        md_cell("""# การสำรวจเชิงสถิติ CIC-IDS2017 (Exploratory Data Analysis)

สำรวจการกระจายตัวของระยะเวลาเชื่อมต่อ (Duration), ปริมาณไบต์ (Forward/Backward Bytes), 
โปรโตคอล (Protocol), และพฤติกรรมการโจมตีตามมาตรฐาน MITRE ATT&CK"""),
        md_cell("""## 1. โหลดข้อมูล Harmonized สำหรับ EDA"""),
        code_cell("""import pandas as pd
import numpy as np
from pathlib import Path

harm_dir = Path("output/harmonized")
features = pd.read_csv(harm_dir / "features.csv")
labels = pd.read_csv(harm_dir / "labels.csv")
meta = pd.read_csv(harm_dir / "metadata.csv")

print(f"Harmonized Records: {len(features):,}")"""),
        md_cell("""## 2. การกระจายตัวของขนาดทราฟฟิกและระยะเวลา"""),
        code_cell("""stats = features[["duration", "bytes_forward", "bytes_backward"]].describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])
display(stats)"""),
        md_cell("""## 3. สรุปความถี่ของประเภทการโจมตี (Attack Taxonomy)"""),
        code_cell("""cat_summary = labels["attack_category"].value_counts().to_frame("count")
cat_summary["percentage"] = (cat_summary["count"] / len(labels) * 100).round(2)
display(cat_summary)""")
    ]
    with open(cic_dir / "eda.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(eda_cells), f, indent=1)

    # 3. feature_engineering.ipynb
    fe_cells = [
        md_cell("""# การสกัดและสร้างฟีเจอร์ CIC-IDS2017 (Feature Engineering)

แปลงฟีเจอร์ระดับโฟลว์ (Flow-level features) ให้อยู่ในรูปแบบฟีเจอร์ร่วม 19 ตัว 
(Log-transformed numerics + One-Hot encoded categoricals)"""),
        code_cell("""from pathlib import Path
import pandas as pd
import numpy as np

harm_dir = Path("output/harmonized")
feat = pd.read_csv(harm_dir / "features.csv")

log_dur = np.log1p(np.maximum(feat["duration"].fillna(0), 0))
log_fwd = np.log1p(np.maximum(feat["bytes_forward"].fillna(0), 0))
log_bwd = np.log1p(np.maximum(feat["bytes_backward"].fillna(0), 0))
signed_ratio = log_fwd - log_bwd

df_num = pd.DataFrame({
    "log_duration": log_dur,
    "log_bytes_forward": log_fwd,
    "log_bytes_backward": log_bwd,
    "signed_log_bytes_ratio": signed_ratio
})
display(df_num.describe())""")
    ]
    with open(cic_dir / "feature_engineering.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(fe_cells), f, indent=1)

    # 4. harmonization.ipynb
    harm_cells = [
        md_cell("""# การประสานโครงสร้าง CIC-IDS2017 (Cross-Dataset Harmonization)

Notebook นี้แมปฟิลด์ต้นทางของ CIC-IDS2017 ให้เข้าสู่มาตรฐานกลาง 22 คอลัมน์ 
พร้อมตรวจสอบความสอดคล้องของ Schema และแยก Labels กับ Metadata ออกจาก Features"""),
        code_cell("""from pathlib import Path
import pandas as pd
import json

harm_dir = Path("output/harmonized")
report = pd.read_csv(harm_dir / "harmonization_report.csv")
display(report)

quality = pd.read_csv(harm_dir / "harmonization_quality.csv")
display(quality)

with open(harm_dir / "provenance.json") as fp:
    prov = json.load(fp)
print(json.dumps(prov, indent=2))""")
    ]
    with open(cic_dir / "harmonization.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(harm_cells), f, indent=1)

def generate_bot_notebooks():
    bot_dir = PROJECT_ROOT / "data-pipeline" / "BoT-IoT"
    
    # 1. cleansing.ipynb
    cleansing_cells = [
        md_cell("""# ทำความสะอาดข้อมูล BoT-IoT (Data Cleansing)

Notebook นี้เตรียมไฟล์ดิบ `BoT_IoT_training-set.csv` และ `BoT_IoT_testing-set.csv` 
จากเซ็นเซอร์เครือข่าย IoT ทำการตรวจสอบ Sentinel Values, NaN, และกำจัดทราฟฟิกซ้ำซ้อน"""),
        md_cell("""## 1. ตรวจสอบพาธและลายนิ้วมือดิจิทัล (SHA-256 Checksum)"""),
        code_cell("""from pathlib import Path
import pandas as pd
import hashlib

raw_dir = Path("raw")
clean_dir = Path("output/cleansing")
clean_dir.mkdir(parents=True, exist_ok=True)

for p in sorted(raw_dir.glob("*.csv")):
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    print(f"File: {p.name:<32} | Size: {p.stat().st_size:>10,} bytes | SHA-256: {h[:16]}...")"""),
        md_cell("""## 2. อ่านรายงานการทำความสะอาด (Cleansing Audit)"""),
        code_cell("""audit_df = pd.read_csv(clean_dir / "cleansing_audit.csv")
display(audit_df)"""),
        md_cell("""## 3. ตรวจสอบข้อมูลหลังคลีนซิ่ง (Cleaned Dataset Distribution)"""),
        code_cell("""train_clean = pd.read_csv(clean_dir / "BoT_IoT_training-set.csv")
print(f"BoT-IoT Cleaned Training Rows: {len(train_clean):,}")
print("\\nAttack Types in Cleaned BoT-IoT:")
print(train_clean["label"].value_counts())""")
    ]
    with open(bot_dir / "cleansing.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(cleansing_cells), f, indent=1)

    # 2. eda.ipynb
    eda_cells = [
        md_cell("""# การสำรวจเชิงสถิติ BoT-IoT (Exploratory Data Analysis)

สำรวจรูปแบบทราฟฟิก IoT เช่น การยิง DoS แบบหนาแน่น, การแสกนพอร์ตอุปกรณ์อัจฉริยะ (Reconnaissance), 
และการโจมตีขโมยรหัสผ่านอุปกรณ์ IoT (Credential Abuse)"""),
        md_cell("""## 1. โหลดข้อมูล Harmonized BoT-IoT"""),
        code_cell("""import pandas as pd
from pathlib import Path

harm_dir = Path("output/harmonized")
features = pd.read_csv(harm_dir / "features.csv")
labels = pd.read_csv(harm_dir / "labels.csv")
meta = pd.read_csv(harm_dir / "metadata.csv")

print(f"Total BoT-IoT Harmonized Flows: {len(features):,}")"""),
        md_cell("""## 2. การกระจายตัวของฟีเจอร์เครือข่าย"""),
        code_cell("""stats = features[["duration", "bytes_forward", "bytes_backward"]].describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])
display(stats)"""),
        md_cell("""## 3. สัดส่วนประเภทการโจมตีตาม MITRE ATT&CK"""),
        code_cell("""cat_summary = labels["attack_category"].value_counts().to_frame("flows")
cat_summary["percentage"] = (cat_summary["flows"] / len(labels) * 100).round(2)
display(cat_summary)""")
    ]
    with open(bot_dir / "eda.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(eda_cells), f, indent=1)

    # 3. feature_engineering.ipynb
    fe_cells = [
        md_cell("""# การสร้างฟีเจอร์ BoT-IoT (Feature Engineering)

แปลงข้อมูลทราฟฟิก IoT ให้อยู่ในรูป Core 19 Features สอดคล้องกับมาตรฐาน Joint Model Profile"""),
        md_cell("""## 1. คำนวณฟีเจอร์ Log Transforms และ Signed Ratio"""),
        code_cell("""import pandas as pd
import numpy as np
from pathlib import Path

harm_dir = Path("output/harmonized")
feat = pd.read_csv(harm_dir / "features.csv")

log_dur = np.log1p(np.maximum(feat["duration"].fillna(0), 0))
log_fwd = np.log1p(np.maximum(feat["bytes_forward"].fillna(0), 0))
log_bwd = np.log1p(np.maximum(feat["bytes_backward"].fillna(0), 0))
signed_ratio = log_fwd - log_bwd

df_num = pd.DataFrame({
    "log_duration": log_dur,
    "log_bytes_forward": log_fwd,
    "log_bytes_backward": log_bwd,
    "signed_log_bytes_ratio": signed_ratio
})
display(df_num.describe())""")
    ]
    with open(bot_dir / "feature_engineering.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(fe_cells), f, indent=1)

    # 4. harmonization.ipynb
    harm_cells = [
        md_cell("""# การประสานโครงสร้าง BoT-IoT (Harmonization)

ตรวจสอบรายงานและคุณภาพการแปลงข้อมูล BoT-IoT เข้าสู่ตารางกลาง"""),
        md_cell("""## 1. ตรวจสอบรายงาน Harmonization และ Provenance"""),
        code_cell("""from pathlib import Path
import pandas as pd
import json

harm_dir = Path("output/harmonized")
report = pd.read_csv(harm_dir / "harmonization_report.csv")
display(report)

quality = pd.read_csv(harm_dir / "harmonization_quality.csv")
display(quality)

with open(harm_dir / "provenance.json") as fp:
    prov = json.load(fp)
print(json.dumps(prov, indent=2))""")
    ]
    with open(bot_dir / "harmonization.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(harm_cells), f, indent=1)

def generate_central_notebooks():
    c_dir = PROJECT_ROOT / "data-pipeline" / "CENTRAL"

    # borderline_smote.ipynb
    smote_cells = [
        md_cell("""# การสังเคราะห์ข้อมูลตัวอย่างกลุ่มน้อยด้วย Borderline-SMOTE (CENTRAL)

Notebook นี้สาธิตและอธิบายขั้นตอนการใช้ **Borderline-SMOTE** 
เพื่อเพิ่มประสิทธิภาพการตรวจจับคลาสที่มีตัวอย่างน้อย (Minority Classes) โดยเฉพาะ **Class 4: Credential Abuse (R2L)**
ให้มีตัวอย่างเพิ่มขึ้นเป็น **40,000 โฟลว์** บนพื้นที่ฟีเจอร์ 19 มิติ โดยไม่สร้าง Noise ในพื้นที่ของ Benign Traffic"""),
        md_cell("""## 1. หลักการทางทฤษฎี: SMOTE ธรรมดา vs Borderline-SMOTE

- **Standard SMOTE**: สุ่มจับคู่ตัวอย่างในคลาสเดียวกันทั้งหมด ทำให้เกิดจุดสังเคราะห์รุกล้ำเข้าไปในคลัสเตอร์ของคลาสส่วนใหญ่ (Benign) ส่งผลให้ False Positive Rate สูงขึ้น
- **Borderline-SMOTE**: คัดกรองเฉพาะตัวอย่างที่อยู่บริเวณ **ขอบเขตการตัดสินใจ (Decision Boundary / DANGER Zone)** โดยพิจารณาจากจำนวนเพื่อนบ้าน $m$ ตัว หากมีเพื่อนบ้านต่างคลาสอยู่ระหว่าง $k/2 \le m \le k$ จุดนั้นจะถูกจัดเป็นขอบเขต และจะทำการสร้างตัวอย่างสังเคราะห์เฉพาะบริเวณนี้"""),
        code_cell("""from pathlib import Path
import json
import pandas as pd
import numpy as np

smote_dir = Path("output/smote")
with open(smote_dir / "smote_report.json") as fp:
    report = json.load(fp)

print("Borderline-SMOTE Execution Report:")
for k, v in report.items():
    print(f"  {k}: {v}")"""),
        md_cell("""## 2. ตรวจสอบการกระจายตัวของคลาสก่อนและหลังการสุ่มตัวอย่าง"""),
        code_cell("""df_before = pd.Series(report["class_distribution_before"], name="Before SMOTE")
df_after = pd.Series(report["class_distribution_after"], name="After SMOTE")

comparison = pd.concat([df_before, df_after], axis=1)
comparison["Net Increase"] = comparison["After SMOTE"] - comparison["Before SMOTE"]
display(comparison)"""),
        md_cell("""## 3. ตรวจสอบความถูกต้องของข้อมูลสังเคราะห์ (Synthetic Flows Inspection)"""),
        code_cell("""labels_smote = pd.read_csv(smote_dir / "labels.csv", low_memory=False)
synthetic_mask = labels_smote["is_synthetic"] == True
print(f"Total Synthetic Rows Generated: {synthetic_mask.sum():,}")
print("\\nSample Synthetic Labels:")
display(labels_smote[synthetic_mask].head(5))""")
    ]
    with open(c_dir / "borderline_smote.ipynb", "w", encoding="utf-8") as f:
        json.dump(make_notebook(smote_cells), f, indent=1)

if __name__ == "__main__":
    generate_cic_notebooks()
    generate_bot_notebooks()
    generate_central_notebooks()
    print("All notebooks generated successfully!")
