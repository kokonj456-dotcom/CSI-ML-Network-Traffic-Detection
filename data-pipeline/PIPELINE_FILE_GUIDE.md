# จัดระเบียบไฟล์ Data Pipeline

อัปเดต 4 พฤศจิกายน 2026: ปรับ CIC-IDS2017, BoT-IoT และ Borderline-SMOTE ให้เดินตามรูปแบบ notebook ของ NSL-KDD/UNSW-NB15

## คำสั่งหลัก

จากโฟลเดอร์โปรเจกต์ `CSI_ML_Final` รัน `python data-pipeline/build_quad_dataset.py` ตัว runner จะอ่านและ execute code cells ใน notebook ตามลำดับ โดยไม่บันทึกผล execution กลับไปทับไฟล์ notebook

## Notebook ที่เป็น implementation

| Notebook | ทำงานอะไร |
|---|---|
| `CIC-IDS2017/cleansing.ipynb` | อ่าน raw CSV, normalize header, เพิ่ม record ID/duplicate flag, export cleaned files และ audit |
| `CIC-IDS2017/harmonization.ipynb` | map raw CIC fields เป็น features/labels/metadata และ export รายงาน |
| `BoT-IoT/cleansing.ipynb` | ขั้น cleansing ที่มี code อยู่ใน notebook โดยตรง |
| `BoT-IoT/harmonization.ipynb` | map `dur/proto/sbytes/dbytes` และ labels เป็น schema กลาง |
| `CENTRAL/borderline_smote.ipynb` | fit Borderline-SMOTE ใน training split ที่เลือก และ export split พร้อม flags |

เปิดแต่ละสมุดแล้วรันทุก cell จากบนลงล่างได้เอง; ไม่มี `run_pipeline.py` หรือ `apply_borderline_smote.py` เป็น implementation คู่กันแล้ว

## ไฟล์ Python ที่ยังเป็นขั้นตอนหลัก

- `build_quad_dataset.py` เป็นตัวจัดลำดับและรัน notebooks
- `CENTRAL/build_dataset.py` เป็น builder สี่ dataset ที่ master runner เรียก
- `audit_all_pipelines.py` เป็น final audit
- `download.py` ของ CIC/BoT ใน checkout นี้สร้างข้อมูลตัวอย่างสังเคราะห์ ไม่ได้ดาวน์โหลด raw benchmark ทางการ; ตรวจ provenance ก่อนใช้งาน

## ไฟล์ที่ลบและไฟล์ที่ยังเก็บ

implementation `.py` รุ่นก่อน, สมุด review-only และ generator เก่าถูกลบออกแล้ว; เส้นทางปัจจุบันใช้ notebook ที่ระบุไว้ด้านบน

`CENTRAL/build_dataset.ipynb` ยังเป็น prototype สำหรับ NSL-KDD/UNSW-NB15 สองชุดและต่างจาก `.py` builder สี่ชุด จึงคงไว้พร้อมคำเตือน ไม่รันสลับกับ builder หลัก ส่วน `CENTRAL/feature_engineering.ipynb` ยังไม่อยู่ใน runnerและยังอ้าง `common/` ที่ไม่มีใน working copy
