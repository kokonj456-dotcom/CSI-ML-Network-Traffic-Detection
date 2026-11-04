# แผนผังไฟล์ Data Pipeline

## คำสั่งหลัก

จาก project root ให้รัน <code>python data-pipeline/build_quad_dataset.py</code>. ตัว runner รัน code cells ใน notebook ตามลำดับโดยไม่เขียน execution output กลับไปทับไฟล์ notebook

## Notebook ที่เป็น implementation

| Notebook | หน้าที่ |
|---|---|
| <code>sub-dataset/NSL-KDD/eda.ipynb</code>, <code>cleansing.ipynb</code>, <code>harmonization.ipynb</code> | สำรวจ ตรวจ/ทำความสะอาด และแปลง NSL-KDD เป็น schema กลาง |
| <code>sub-dataset/UNSW-NB15/eda.ipynb</code>, <code>cleansing.ipynb</code>, <code>harmonization.ipynb</code> | สำรวจ ทำความสะอาด และแปลง UNSW-NB15 เป็น schema กลาง |
| <code>sub-dataset/CIC-IDS2017/cleansing.ipynb</code> | อ่านและจัดรูป raw input พร้อม audit |
| <code>sub-dataset/CIC-IDS2017/harmonization.ipynb</code> | สร้าง features, labels และ metadata ตาม schema กลาง |
| <code>sub-dataset/BoT-IoT/cleansing.ipynb</code> | ทำความสะอาดข้อมูล BoT-IoT |
| <code>sub-dataset/BoT-IoT/harmonization.ipynb</code> | map ข้อมูล BoT-IoT เป็น schema กลาง |
| <code>CENTRAL/build_dataset.ipynb</code> | รวม harmonized tables ทั้งสี่ชุดและสร้าง splits |
| <code>CENTRAL/borderline_smote.ipynb</code> | สร้างตัวอย่างสังเคราะห์เฉพาะ train และ train_full |

เปิด notebook แล้วรัน cell จากบนลงล่างได้เอง โค้ดสร้าง CENTRAL อยู่ใน <code>build_dataset.ipynb</code> โดยตรง; ไม่มี <code>build_dataset.py</code> ที่เป็น implementation คู่กัน

## ไฟล์ Python ที่ยังทำหน้าที่ orchestration/audit

- <code>build_quad_dataset.py</code> จัดลำดับและ execute notebooks
- <code>audit_all_pipelines.py</code> ตรวจ output จากแต่ละ dataset, splits และ SMOTE
- downloader ของแต่ละชุดใช้เตรียม raw input; downloader CIC/BoT อาจ fallback ไปสร้างข้อมูลตัวอย่าง หากโหลดแหล่งออนไลน์ไม่สำเร็จ

## Notebook วิเคราะห์แยกจาก runner

- <code>CENTRAL/analyze_dataset_relationships.ipynb</code> เปรียบเทียบความสัมพันธ์และการกระจายของ NSL-KDD/UNSW-NB15 จาก train_full; โค้ดวิเคราะห์อยู่ใน notebook โดยตรง
- <code>CENTRAL/eda.ipynb</code> สำรวจ harmonized data ของ NSL-KDD/UNSW-NB15
- <code>CENTRAL/analyze_dataset_relationships.ipynb</code> วิเคราะห์ distribution ของ NSL-KDD/UNSW-NB15 จาก train_full
- <code>CENTRAL/feature_engineering.ipynb</code> เป็นเส้นทาง preprocessing ทางเลือก ไม่ได้อยู่ใน master runner; ตัวแทนนี้ใช้ scaler/encoder ต่างจาก representation ภายใน SMOTE จึงอย่ารวม CSV สองทางเข้าด้วยกัน

ดูหน้าที่และ input/output ของ CENTRAL ได้ใน <code>CENTRAL/README.md</code>.
