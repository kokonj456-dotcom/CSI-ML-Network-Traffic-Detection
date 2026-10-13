# NIDS Multi-Dataset Pipeline & Benchmark Dashboard

เว็บ Dashboard สำหรับสำรวจ EDA, สถิติเชิงพรรณนา, คุณภาพข้อมูลจาก cleansing, ผล feature engineering และการเปรียบเทียบผลลัพธ์โมเดลแบบครบวงจร

รองรับ 3 มุมมองชุดข้อมูล:
1. NSL-KDD
2. UNSW-NB15
3. Common (Harmonized Merged Dataset)

---

## โครงสร้างโปรเจกต์

```text
webapp/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI application, routing, CORS
│   │   └── data_loader.py   # Multi-dataset loader, hybrid sampling, metrics aggregation
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx          # React application, multi-tab layout, 2-tier model comparator
    │   ├── main.jsx
    │   └── index.css
    ├── index.html
    ├── package.json
    └── vite.config.js       # Reverse proxy /api ไปยัง FastAPI พอร์ต 8000
```

---

## ฟังก์ชันการทำงานหลัก

1. Multi-Dataset Switcher:
   - สลับมุมมองข้อมูลระหว่าง Common Merged, NSL-KDD และ UNSW-NB15 ได้จากเมนูด้านบน
2. EDA & Distributions (100% Full Dataset Processing):
   - คำนวณสถิติและแจกแจงจากข้อมูลเต็ม 100% ครบทุกแถว (Common: 406,190 แถว, NSL-KDD: 148,517 แถว, UNSW-NB15: 257,673 แถว)
   - กรองตาม Split จริง (เช่น KDDTrain, KDDTest, KDDTest-21, Train/Val/Test)
   - สถิติ Normal vs Attack, Attack Categories และ Protocols สะท้อนยอดรวมจริงทั้งหมด
   - ปรับการเรนเดอร์ Scatter Plot ให้เสถียรด้วย uniform sampling 1,000 จุดป้องกันการแล็กของเบราว์เซอร์
3. Data Cleansing & Quality:
   - สรุปผลการตรวจสอบความสมบูรณ์ของข้อมูล, นโยบายการจัดการค่าสูญหาย และรายงาน cleansing audit
4. Feature Engineering & Contract:
   - สำรวจ Candidate Features จาก feature_contract.json และรายการฟิลด์ที่ตัดออกเพื่อป้องกัน Data Leakage
5. Models & Comparison (Full Evaluation Integration):
   - รองรับผลการทดลองจริงจาก 4 สถาปัตยกรรมโมเดล: XGBoost, MLP, Autoencoder, Isolation Forest
   - ระบบ 2-Tier Selector:
     - ขั้นตอนที่ 1: เลือก Model Family หลัก
     - ขั้นตอนที่ 2: เลือก Checkpoint Run ของ Family นั้น
   - ตารางเปรียบเทียบค่า Delta Diff (+Δ% / -Δ%) พร้อมระบุฝ่ายที่ได้เปรียบ
   - Confusion Matrix Face-Off แบบเคียงข้างกัน และสลับดูผลได้ทั้ง KDDTest+ และ KDDTest-21
   - Hyperparameter Inspection & Comparison: ตารางเปรียบเทียบพารามิเตอร์การเทรนของ Model A และ Model B แบบเคียงข้างกัน
6. Model Training Studio (On-Demand Training Engine):
   - เลือกสถาปัตยกรรมโมเดลที่ต้องการเทรนได้ทั้ง 4 ตระกูล: XGBoost, MLP (PyTorch), Autoencoder (PyTorch), Isolation Forest
   - เลือกชุดข้อมูลที่ต้องการใช้เทรนและทดสอบ: Common Harmonized (406k rows), NSL-KDD (148k rows), หรือ UNSW-NB15 (257k rows)
   - ปรับแต่ง Hyperparameters ผ่าน UI ได้แบบยืดหยุ่น (Estimators, Depth, Learning Rate, Epochs, Batch Size, Threshold, Contamination ฯลฯ)
   - สั่งเทรนสดผ่านระบบ Live API และบันทึก Checkpoint ลงระบบอัตโนมัติ
   - แสดงผลประเมินทันทีหลังเทรนเสร็จ พร้อมปุ่มส่งผลลัพธ์เข้า 2-Tier Comparator ทันที
   - ตาราง Training History & Hyperparameter Audit Log บันทึกประวัติและพารามิเตอร์ของทุกการทดลอง

---

## วิธีเปิดใช้งาน

1. เริ่มต้น FastAPI Backend:
```bash
python -m uvicorn app.main:app --app-dir webapp/backend --host 127.0.0.1 --port 8000
```
- API Docs: http://127.0.0.1:8000/docs

2. เริ่มต้น Vite React Frontend:
```bash
cd webapp/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```
- Web Application: http://127.0.0.1:5173
