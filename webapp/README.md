# NSL-KDD Dashboard

เว็บ Dashboard สำหรับสำรวจ EDA, สถิติเชิงพรรณนา, คุณภาพข้อมูลจาก cleansing และผล feature engineering

> หมายเหตุ: ใน checkout ปัจจุบันมีเฉพาะคู่มือเตรียม Dashboard นี้; source code ของ `backend/` และ `frontend/` ยังไม่ได้อยู่ใน repository

## โครงสร้าง

```text
webapp/
├── backend/
│   ├── app/                 # FastAPI, data loading, filter logic, analytics
│   ├── tests/               # ทดสอบ filter และข้อมูลที่ API ส่งให้หน้าเว็บ
│   └── requirements.txt
└── frontend/
    ├── src/                 # React UI, tabs, shared filters, Plotly charts
    ├── package.json
    └── vite.config.js       # ส่ง /api ไปยัง FastAPI ระหว่างพัฒนา
```

## เตรียมข้อมูล

Dashboard อ่านไฟล์ที่ pipeline สร้างไว้ ไม่แก้ไขข้อมูลและไม่รัน notebook ให้อัตโนมัติ หากข้อมูลยังไม่มี ให้ทำตามนี้จากโฟลเดอร์รากของ repository:

```powershell
python data-pipeline/NSL-KDD/download.py
```

จากนั้นรัน `data-pipeline/NSL-KDD/eda.ipynb`, `cleansing.ipynb` และ `feature_engineering.ipynb` เพื่อเตรียมหน้าสำรวจ NSL-KDD แบบเดิม หากต้องการสร้างตารางกลาง ให้รัน `data-pipeline/NSL-KDD/harmonization.ipynb` แล้วตามด้วย `data-pipeline/common/build_dataset.ipynb` และ `feature_engineering.ipynb` ตามคู่มือ [`data-pipeline/README.md`](../data-pipeline/README.md)

## เปิดใช้งานในเครื่อง

เปิด PowerShell หน้าต่างแรกจากโฟลเดอร์รากของ repository:

```powershell
python -m pip install -r webapp/backend/requirements.txt
python -m uvicorn app.main:app --app-dir webapp/backend --reload --host 127.0.0.1 --port 8000
```

เปิด PowerShell หน้าต่างที่สอง:

```powershell
cd webapp/frontend
npm install
npm run dev
```

เปิด URL ที่ Vite แสดงใน terminal (ปกติคือ `http://127.0.0.1:5173`) เอกสาร API อยู่ที่ `http://127.0.0.1:8000/docs`

หน้าเว็บมีตัวกรองร่วมแบบ sticky; การคลิกกลุ่มบนกราฟหรือเลือก filter จะอัปเดตทุกแท็บ EDA, Descriptive, Cleansing และ Feature Engineering โดยเลือกทุก split เป็นค่าเริ่มต้น หน้า Models & Comparison เป็นพื้นที่เตรียมไว้และยังไม่แสดงผล evaluation

## การตรวจสอบ

```powershell
python -m pip install -r webapp/backend/requirements-dev.txt
python -m pytest webapp/backend/tests
```

```powershell
cd webapp/frontend
npm run build
npm test
```
