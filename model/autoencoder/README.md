# Autoencoder Anomaly Detection

ระบบตรวจจับความผิดปกติของ Network Traffic (NIDS) ด้วย Autoencoder โดยใช้ชุดข้อมูล **NSL-KDD** จากขั้นตอน `feature_engineered`

---

## 1. การทำงานและโครงสร้างฟีเจอร์

1. **แหล่งข้อมูล**: อ่านข้อมูลจาก `data-pipeline/output/NSL-KDD/feature_engineered/`
   - `KDDTrain_features.csv` และ `KDDTrain_targets.csv` (157 คอลัมน์)
   - `KDDTest_features.csv` และ `KDDTest_targets.csv`
   - `KDDTest-21_features.csv` และ `KDDTest-21_targets.csv`
2. **การคัดกรองฟีเจอร์**:
   - กรองเฉพาะทราฟฟิกปกติ (`is_attack == 0`) สำหรับฝึกโมเดลแบบ Unsupervised
   - ตัดคอลัมน์คงที่ (Constant Columns ที่มีค่าเดียวบน Normal Training) จำนวน 47 คอลัมน์ออก
   - เหลือฟีเจอร์ใช้งานจริง **110 ฟีเจอร์** (บันทึกไว้ใน `feature_columns.txt`)
3. **การสเกลข้อมูล**: ใช้ `StandardScaler` โดย `fit` เฉพาะบน Normal Training Data แล้วบันทึกไว้ใน `scaler.pkl`
4. **สถาปัตยกรรมโมเดล Autoencoder**:
   - **Encoder**: `Input (110) → Linear(64) → ReLU → Linear(32) → ReLU → Linear(16) → ReLU → Linear(8)`
   - **Decoder**: `Linear(8) → ReLU → Linear(16) → ReLU → Linear(32) → ReLU → Linear(64) → ReLU → Linear(110)`
   - Loss Function: `MSELoss` (วัด Reconstruction Error)
   - Optimizer: `Adam`

---

## 2. วิธีการติดตั้ง (Setup Environment)

เปิด PowerShell ที่โฟลเดอร์หลักของโปรเจกต์ (`CSI_ML_Final`):

```powershell
# สร้างและเปิดใช้งาน Virtual Environment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# ติดตั้ง Dependencies
python -m pip install -r model/autoencoder/requirements.txt
python -m pip install -r model/autoencoder/webapp/requirements-webapp.txt
```

---

## 3. การฝึกโมเดลใหม่ (Training)

รันสคริปต์ `train.py` เพื่อฝึกโมเดล Autoencoder จากข้อมูลในโฟลเดอร์ `feature_engineered`:

```powershell
python model/autoencoder/train.py --epochs 25 --batch-size 256 --lr 0.001 --threshold-percentile 95.0
```

### พารามิเตอร์ที่สามารถปรับแต่งได้:
| Parameter | Default | คำอธิบาย |
|---|:---:|---|
| `--epochs` | `25` | จำนวนรอบการฝึก |
| `--batch-size` | `256` | ขนาดมินิแบตช์ |
| `--lr` | `0.001` | อัตราการเรียนรู้ (Learning Rate) |
| `--seed` | `42` | Random Seed เพื่อ Reproducibility |
| `--val-size` | `0.20` | สัดส่วนแบ่งชุด Validation สำหรับหา Threshold |
| `--threshold-percentile` | `95.0` | เปอร์เซ็นไทล์ของ Validation Reconstruction Error สำหรับใช้เป็น Threshold |
| `--skip-eval` | - | ใส่แฟล็กนี้หากไม่ต้องการประเมินบน Test Set ทันทีหลังเทรนเสร็จ |
| `--device` | `auto` | เลือก `auto`, `cuda` หรือ `cpu` |

### ไฟล์ผลลัพธ์ที่จะถูกบันทึกอัตโนมัติ:
- `autoencoder.pth`: น้ำหนักโมเดลที่ดีที่สุด (บันทึกจาก Epoch ที่ให้ Validation Loss ต่ำสุด)
- `scaler.pkl`: ตัวสเกลเลอร์ที่ fit ไว้
- `feature_columns.txt`: รายชื่อ 110 ฟีเจอร์ที่โมเดลใช้งานจริง
- `training_history.csv`: บันทึก Train Loss และ Validation Loss ในแต่ละ Epoch

---

## 4. การประเมินผลโมเดล (Evaluation)

### 4.1 ประเมินผลภาพรวม (Accuracy, Precision, Recall, F1, Confusion Matrix)
```powershell
# ประเมินบนชุด KDDTest มาตรฐาน
python model/autoencoder/evaluate.py --dataset KDDTest --percentile 95.0

# ประเมินบนชุด KDDTest-21 ระดับยาก
python model/autoencoder/evaluate.py --dataset KDDTest-21 --percentile 95.0
```

### 4.2 ประเมินการตรวจจับ Known vs Unseen (Zero-day) Attacks
```powershell
# ประเมินแยกตามประเภทการโจมตี Known/Unseen บน KDDTest
python model/autoencoder/evaluate_unseen.py --dataset KDDTest

# ประเมินบน KDDTest-21
python model/autoencoder/evaluate_unseen.py --dataset KDDTest-21
```

รายงานจะถูกบันทึกเป็นไฟล์ CSV:
- `unseen_attack_results_<dataset>.csv`: สรุป Detection Rate แยกตามประเภทการโจมตี
- `unseen_attack_details_<dataset>.csv`: ผลการทำนายและ Reconstruction Error รายแถว

---

## 5. การเปิดใช้งาน Web Application Dashboard

รันเซิร์ฟเวอร์ FastAPI:

```powershell
python -m uvicorn model.autoencoder.webapp.main:app --host 127.0.0.1 --port 8000
```

เปิดเบราว์เซอร์ไปที่:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

สามารถเลือกทดลองโมเดลเดิม หรือกดสั่งเทรนโมเดลใหม่ผ่านหน้าเว็บได้โดยตรง พร้อมทั้งดูกราฟ Confusion Matrix, Error Distribution และ Detection Rate

---

## 6. สคริปต์วิเคราะห์และการทดลอง (Analysis & Experiment Scripts)

สคริปต์ในโฟลเดอร์ `scripts/` แบ่งออกเป็น 4 กลุ่ม:
- `scripts/data_checks/`: ตรวจสอบตัวอย่างข้อมูลและการกระจายตัวของค่า Error
- `scripts/analysis/`: วิเคราะห์ Reconstruction Error รายฟีเจอร์, Missed Attacks และ Unseen Attacks
- `scripts/experiments/`: ทดลอง Scoring Methods เช่น MSE vs Top-K Features, Threshold Percentile และ Hybrid Scoring
- `scripts/visualization/`: สร้างกราฟ Confusion Matrix, Error Distribution และ Detection Rate

### วิธีรันสคริปต์ทั้งหมดอัตโนมัติ:
```powershell
python model/autoencoder/scripts/run_all_scripts.py
```

ผลลัพธ์ทั้งหมดจะถูกส่งออกไปยัง:
- **`model/autoencoder/results/csv/`**: ไฟล์ข้อมูลสรุปและตารางรายงานทั้งหมด (28 ไฟล์)
- **`model/autoencoder/results/png/`**: กราฟและแผนภาพสรุปผลทั้งหมด (6 ไฟล์)