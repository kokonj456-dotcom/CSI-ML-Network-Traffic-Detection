# CSI ML Final

โปรเจกต์นี้จัดโฟลเดอร์ตามหน้าที่: ข้อมูลต้นทาง, ขั้นตอนเตรียมข้อมูล, โค้ดโมเดล และเว็บแอป

## โครงสร้าง

```text
CSI_ML_Final/
├── data-pipeline/
│   ├── NSL-KDD/                  # raw, notebooks, docs และ output ของ NSL
│   ├── UNSW-NB15/                # raw และ pipeline เฉพาะ UNSW
│   └── common/                   # notebook รวมข้อมูล, registry, contract และเอกสาร dataset กลาง
├── model/
│   ├── README.md                 # แนวทางเพิ่มโมเดลของสมาชิกในทีม
│   └── isolation-forest/
│       ├── train.py              # จุดเริ่มต้นสำหรับรันเทรน
│       ├── src/                  # โมดูล data, training, evaluation และ reporting
│       └── requirements.txt
└── webapp/
    └── README.md                 # คู่มือ/แผน React + FastAPI; source ยังไม่อยู่ใน checkout นี้
```

## เริ่มต้นใช้งาน

1. ดาวน์โหลด NSL-KDD จากโฟลเดอร์รากของ repository:

   ```powershell
   python data-pipeline/NSL-KDD/download.py
   ```

2. สำหรับ NSL-KDD ให้รัน EDA, Cleansing และ Harmonization; สำหรับ UNSW-NB15 ให้วางไฟล์ train/test ทางการใน `data-pipeline/UNSW-NB15/raw/` แล้วรัน `download.py`, EDA, Cleansing และ Harmonization ตามลำดับ

3. สำหรับ Dataset กลาง ติดตั้ง `data-pipeline/requirements.txt` แล้วรัน `data-pipeline/common/build_dataset.ipynb` และ `feature_engineering.ipynb` ตามลำดับ ขอบเขตปัจจุบันมี NSL-KDD และ UNSW-NB15 เท่านั้น; อ่าน [คู่มือ pipeline](data-pipeline/README.md) สำหรับขั้นตอนและสถานะข้อมูล

4. สำหรับ Isolation Forest/MLP รุ่นที่ใช้ NSL-KDD เดิม ให้รัน NSL `cleansing.ipynb` และ `feature_engineering.ipynb` ก่อน แล้วติดตั้ง dependency และรัน Isolation Forest:

   ```powershell
   python -m pip install -r model/isolation-forest/requirements.txt
   python model/isolation-forest/train.py --alert-rate 0.05 --clusters 5
   ```

ผลลัพธ์ของ NSL-KDD อยู่ใต้ `data-pipeline/NSL-KDD/output/` แยกเป็น `cleansing/`, `harmonized/`, `feature_engineering/` และ `model_runs/` ส่วนชุดข้อมูลกลางอยู่ใน `data-pipeline/common/output/`; raw data และผลลัพธ์ที่สร้างซ้ำได้ถูกละเว้นจาก Git.

## Dataset กลาง

โฟลเดอร์ `data-pipeline/common/` เก็บทะเบียน dataset, สัญญาความหมายของ feature, notebook รวมข้อมูล และผลลัพธ์กลาง การนำ NSL-KDD และ UNSW-NB15 เข้าร่วมจะผ่านการตรวจ schema, หน่วย, แถวซ้ำ และความพร้อมของ feature ก่อนสร้างไฟล์รวม ดูขั้นตอนและสถานะชุดข้อมูลได้ใน [`data-pipeline/README.md`](data-pipeline/README.md).

## Dashboard ที่วางแผนไว้

แผน Dashboard คือ React + FastAPI แบบ read-only สำหรับสำรวจ EDA, สถิติเชิงพรรณนา, cleansing และ feature engineering พร้อมตัวกรองร่วมแบบ sticky และเชื่อมข้ามแท็บ ปัจจุบัน checkout นี้มีเฉพาะคู่มือใน [`webapp/README.md`](webapp/README.md); source frontend/backend ยังไม่พร้อมให้เปิดใช้งาน
