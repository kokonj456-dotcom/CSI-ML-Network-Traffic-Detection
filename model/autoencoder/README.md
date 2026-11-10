# Autoencoder Anomaly Detection

ระบบตรวจจับความผิดปกติของ Network Traffic (NIDS) ด้วย Autoencoder แบบ Unsupervised Anomaly Detection โดยใช้ชุดข้อมูลรวมศูนย์ **CENTRAL Quad-Dataset** (`NSL-KDD`, `UNSW-NB15`, `CIC-IDS2017`, `BoT-IoT`) รวม 747,504 โฟลว์ บนพื้นที่ฟีเจอร์ร่วม 19 มิติ (19 Core Features)

---

## 1. โครงสร้างโฟลเดอร์ (Folder Structure)

```text
model/autoencoder/
├── backup/                 # ประวัติการทดลองและโมเดลที่บันทึกแยกตาม Run ID
├── autoencoder_model.py    # สถาปัตยกรรมโครงข่ายประสาทเทียม Autoencoder (PyTorch)
├── train.py                # สคริปต์หลักสำหรับการฝึกและประเมินผลโมเดล
├── train_common.py         # สคริปต์ฝึกโมเดลบนชุดข้อมูลกลาง Harmonized Multi-Dataset
├── evaluate.py             # สคริปต์ประเมินผลบนชุดทดสอบ Global Benchmark และแยกตาม Dataset/Taxonomy
├── compare_training_methods.py # สคริปต์เปรียบเทียบ 4 วิธีฝึก (SMOTE vs Weight R2L Ablation)
├── feature_columns.txt     # รายชื่อ 19 ฟีเจอร์ที่โมเดลใช้งานจริง
├── scaler.pkl              # ตัวสเกลเลอร์ StandardScaler ที่ fit บน Normal Data
├── autoencoder.pth         # น้ำหนักโมเดล Autoencoder ล่าสุด
├── requirements.txt        # ไลบรารีที่จำเป็น (PyTorch, scikit-learn, pandas)
└── README.md               # เอกสารอธิบายการใช้งาน
```

---

## 2. การทำงานและโครงสร้างฟีเจอร์

1. **แหล่งข้อมูล (CENTRAL Quad-Dataset)**:
   - อ่านข้อมูลจาก `data-pipeline/CENTRAL/output/splits/`
   - `train`: 482,104 โฟลว์ (มีข้อมูล Normal สำหรับฝึก 195,614 โฟลว์)
   - `validation`: 120,524 โฟลว์ (มีข้อมูล Normal 48,940 โฟลว์ สำหรับตรวจสอบและหา Alert Threshold)
   - `test`: 144,876 โฟลว์ สำหรับ Global Multi-Domain Benchmark
2. **ฟีเจอร์ 19 มิติ (19 Core Joint Features)**:
   - **4 Numeric Features**: `log_duration`, `log_bytes_forward`, `log_bytes_backward`, `signed_log_bytes_ratio`
   - **4 Protocol One-Hot**: `proto_tcp`, `proto_udp`, `proto_icmp`, `proto_other`
   - **7 Service One-Hot**: `service_dns`, `service_ftp`, `service_http`, `service_https_ssl`, `service_smtp`, `service_ssh`, `service_other`
   - **4 State One-Hot**: `state_established`, `state_no-reply`, `state_reset`, `state_other`
3. **การสเกลข้อมูล**: ใช้ `StandardScaler` โดย `fit` เฉพาะบน Normal Training Data
4. **สถาปัตยกรรมโมเดล Autoencoder (Symmetric Bottleneck)**:
   - **Encoder**: `Input (19) → Linear(14) → ReLU → Linear(8) → ReLU → Linear(4)`
   - **Decoder**: `Linear(4) → ReLU → Linear(8) → ReLU → Linear(14) → ReLU → Linear(19)`
   - Loss Function: `MSELoss` (วัด Reconstruction Error)
   - Optimizer: `Adam`
   - การตัดเกณฑ์ (Threshold): คำนวณจากเปอร์เซ็นไทล์ของ Reconstruction Error บนชุดข้อมูลปกติของ Validation

---

## 3. วิธีการติดตั้ง (Setup Environment)

```powershell
python -m pip install -r model/autoencoder/requirements.txt
```

---

## 4. การฝึกโมเดล (Training)

### วิธีที่ 1: รันผ่าน `train_common.py` (รูปแบบเดียวกับ XGBoost / Isolation Forest)
```powershell
python model/autoencoder/train_common.py --epochs 20 --batch-size 512
```

### วิธีที่ 2: รันผ่าน `train.py` พร้อมปรับแต่งพารามิเตอร์
```powershell
python model/autoencoder/train.py --epochs 20 --batch-size 512 --lr 0.001 --threshold-percentile 95.0
```

#### พารามิเตอร์ที่สามารถปรับแต่งได้:
| Parameter | Default | คำอธิบาย |
|---|:---:|---|
| `--epochs` | `20` | จำนวนรอบการฝึก |
| `--batch-size` | `512` | ขนาดมินิแบตช์ |
| `--lr` | `0.001` | อัตราการเรียนรู้ (Learning Rate) |
| `--seed` | `42` | Random Seed เพื่อความเสถียรของผลลัพธ์ |
| `--train-split` | `train` | ชุดข้อมูลฝึก (`train` หรือ `train_smote`) |
| `--threshold-percentile` | `95.0` | เปอร์เซ็นไทล์ของ Validation Reconstruction Error สำหรับ Alert Threshold |
| `--skip-eval` | - | ข้ามการประเมินผลบน Test Set ทันทีหลังเทรนเสร็จ |
| `--device` | `auto` | เลือก `auto`, `cuda` หรือ `cpu` |

ผลลัพธ์ของแต่ละ Run จะถูกจัดเก็บอัตโนมัติในโฟลเดอร์ `model/autoencoder/backup/<run_id>/`

---

## 5. การประเมินผลโมเดล (Evaluation)

### ประเมินผลบน Global Test Set ทั้งหมด (144,876 โฟลว์):
```powershell
python model/autoencoder/evaluate.py --split test --dataset all
```

### ประเมินผลเจาะจงเฉพาะชุดข้อมูลย่อย:
```powershell
python model/autoencoder/evaluate.py --split test --dataset NSL-KDD
python model/autoencoder/evaluate.py --split test --dataset UNSW-NB15
python model/autoencoder/evaluate.py --split test --dataset CIC-IDS2017
python model/autoencoder/evaluate.py --split test --dataset BoT-IoT
```

### ประเมินผลการตรวจจับข้ามโดเมนและ Novel Attacks:
```powershell
python model/autoencoder/evaluate.py --split test --unseen
```

---

## 6. การทดลองเปรียบเทียบ 4 วิธีฝึก (SMOTENC & R2L Weight Ablation Study)

สคริปต์ `compare_training_methods.py` ใช้สำหรับการทดลองและเปรียบเทียบกลยุทธ์การรับมือปัญหาความไม่สมดุลของข้อมูล (Class Imbalance) ทั้ง 4 วิธี เพื่อประเมินผลกระทบต่อค่า Accuracy, Precision, Recall และ F1-score:

```powershell
python model/autoencoder/compare_training_methods.py --epochs 8 --r2l-weight 5.0
```

### ตารางสรุป 4 วิธีฝึก:
1. **ไม่ทำ SMOTE ไม่เพิ่ม weight**: Baseline train split โดยไม่มีการถ่วงน้ำหนัก
2. **ไม่ทำ SMOTE + weight R2L**: Baseline train split ร่วมกับการเพิ่ม weight/penalty ให้กับการตรวจจับ R2L (Class 4)
3. **ทำ SMOTENC**: ฝึกด้วยชุดข้อมูล `train_smote` (สังเคราะห์ R2L เพิ่ม 40,000 โฟลว์) โดยไม่เพิ่ม weight
4. **ทำ SMOTENC + weight R2L**: ฝึกด้วยชุดข้อมูล `train_smote` ร่วมกับการเพิ่ม weight ให้ R2L

ผลลัพธ์จะแสดงเป็นตารางสรุปในหน้าต่าง Terminal พร้อมบันทึกไฟล์:
- `model/autoencoder/COMPARISON_TABLE.md` (รายงาน Markdown)
- `model/autoencoder/comparison_results.json` (ข้อมูล JSON แบบละเอียด)

