# Autoencoder WebApp — Backup style แบบเดียวกับ MLP

หน้าเว็บทดลอง Autoencoder ภาษาไทย ใช้ FastAPI และบันทึกประวัติลงไฟล์ JSON/CSV โดยไม่ใช้ SQL หรือ SQLite

## วางไฟล์
นำโฟลเดอร์ `webapp` ไปไว้ที่ `model/autoencoder/webapp/`

## ติดตั้ง (รันจาก root ของ CSI_ML_Final-main)
```powershell
.\.venv\Scripts\python.exe -m pip install -r .\model\autoencoder\webapp\requirements-webapp.txt
```

## เปิดเว็บ
```powershell
.\.venv\Scripts\python.exe -m uvicorn model.autoencoder.webapp.main:app --host 127.0.0.1 --port 8000
```
เปิด `http://127.0.0.1:8000`

## รูปแบบ Backup
ผลจะถูกบันทึกใน `model/autoencoder/Backup/`
```text
Backup/
├── experiment_history.csv
└── runs/
    └── AE_YYYYMMDD_HHMMSS_xxxxxx/
        ├── experiment.json
        ├── config.json
        ├── metrics.json
        ├── confusion_matrix.json
        ├── detection_by_attack.json
        ├── detection_by_attack.csv
        ├── record_details.csv
        ├── training_history.csv       # มีเมื่อเลือกฝึกโมเดลใหม่
        ├── autoencoder.pth            # มีเมื่อเลือกฝึกโมเดลใหม่
        ├── scaler.pkl                 # มีเมื่อเลือกฝึกโมเดลใหม่
        ├── feature_columns.txt        # มีเมื่อเลือกฝึกโมเดลใหม่
        └── plots/
            ├── confusion_matrix.png
            ├── reconstruction_error_distribution.png
            └── training_curves.png    # มีเมื่อเลือกฝึกโมเดลใหม่
```

- `experiment_history.csv` เป็นตารางสรุปทุกรอบ คล้ายกับ MLP
- `experiment.json` เก็บสถานะและสรุปผลการทดลองของรอบนั้น
- `config.json` เก็บค่าที่ใช้ในการรัน
- `metrics.json` เก็บผลประเมินจริง
- `plots/` เก็บกราฟ PNG ของรอบนั้น
- ไม่ใช้ SQL/SQLite
- การเทรนใหม่ไม่เขียนทับ `autoencoder.pth` หลัก แต่บันทึกโมเดลลงโฟลเดอร์ Backup ของรอบนั้น

## หมายเหตุ
- ต้องมี `autoencoder_model.py`, `autoencoder.pth`, `scaler.pkl`, `feature_columns.txt` ใน `model/autoencoder/` สำหรับโหมดใช้โมเดลเดิม
- ต้องมีชุดข้อมูล feature-engineered ใน `data-pipeline/output/NSL-KDD/feature_engineered/`
- คอลัมน์เป้าหมายต้องมี `is_attack` (0=Normal, 1=Attack)
- กราฟ PNG ต้องใช้ matplotlib ซึ่งรวมไว้ใน requirements
- ทดสอบการเทรนหนึ่งรอบก่อนใช้งานจริง และตรวจสอบไฟล์ที่สร้างใน `Backup/runs/`
