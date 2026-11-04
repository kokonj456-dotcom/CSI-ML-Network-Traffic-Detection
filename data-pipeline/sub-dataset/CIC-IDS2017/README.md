# CIC-IDS2017 Pipeline

## Workflow

รัน notebook ตามลำดับ `cleansing.ipynb` → `harmonization.ipynb`; แต่ละเล่มมีโค้ดประมวลผลอยู่ในตัวและสร้างผลใน `output/`. `eda.ipynb` ใช้สำรวจผลหลัง harmonization. master runner `../build_quad_dataset.py` จะ execute cleansing และ harmonization โดยอัตโนมัติเมื่อยังไม่มี `output/harmonized/features.csv`.

Raw files expected: `CIC_IDS2017_training-set.csv / CIC_IDS2017_testing-set.csv`.

## Source provenance

ใน working copy นี้ `download.py` สร้างข้อมูลตัวอย่างสังเคราะห์ ไม่ได้ดาวน์โหลด raw benchmark ทางการ ห้ามเรียก output นี้ว่าข้อมูล official CIC-IDS2017/BoT-IoT; ดู `output/RUN_PROVENANCE.json` ก่อนตีความผล

ดู [`../../PIPELINE_FILE_GUIDE.md`](../../PIPELINE_FILE_GUIDE.md) สำหรับบทบาทไฟล์และคำสั่งรวม
