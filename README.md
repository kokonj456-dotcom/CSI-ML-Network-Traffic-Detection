# CSI ML Final

โปรเจกต์นี้จัดโฟลเดอร์ตามหน้าที่: ข้อมูลต้นทาง, ขั้นตอนเตรียมข้อมูล, โค้ดโมเดล และเว็บแอป

## โครงสร้าง

```text
CSI_ML_Final/
├── dataset/
│   ├── download_nsl_dataset.py   # ดาวน์โหลด NSL-KDD
│   └── rawdata/NSL-KDD/          # ข้อมูลดิบในเครื่อง (ไม่อัปโหลด Git)
├── data-pipeline/
│   ├── nsl_eda.ipynb             # สำรวจข้อมูล
│   ├── nsl_cleansing.ipynb       # ทำความสะอาดข้อมูล
│   ├── nsl_feature_engineering.ipynb
│   ├── nsl_feature_engineering.md
│   └── output/NSL-KDD/           # ผลลัพธ์ที่สร้างจาก pipeline (ไม่อัปโหลด Git)
├── model/
│   ├── README.md                 # แนวทางเพิ่มโมเดลของสมาชิกในทีม
│   └── isolation-forest/
│       ├── train.py              # จุดเริ่มต้นสำหรับรันเทรน
│       ├── src/                  # โมดูล data, training, evaluation และ reporting
│       └── requirements.txt
└── webapp/                       # ส่วนเว็บแอป
```

## เริ่มต้นใช้งาน

1. ดาวน์โหลดข้อมูลจากโฟลเดอร์รากของ repository:

   ```powershell
   python dataset/download_nsl_dataset.py
   ```

2. เปิดและรัน notebook ตามลำดับ: `nsl_eda.ipynb` (ถ้าต้องการสำรวจ), `nsl_cleansing.ipynb`, แล้ว `nsl_feature_engineering.ipynb` ใน `data-pipeline/`.

3. ติดตั้ง dependency และรัน Isolation Forest:

   ```powershell
   python -m pip install -r model/isolation-forest/requirements.txt
   python model/isolation-forest/train.py --alert-rate 0.05 --clusters 5
   ```

ผลลัพธ์ของ pipeline และโมเดลอยู่ใต้ `data-pipeline/output/NSL-KDD/` แยกตามขั้นตอน (`clean/`, `feature_engineered/`, `isolation_forest/`) และถูกละเว้นจาก Git เพราะสร้างซ้ำได้จากข้อมูลต้นทางกับโค้ด.
