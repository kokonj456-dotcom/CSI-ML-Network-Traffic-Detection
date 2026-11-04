# การทดลองโมเดล MLP (Multi-Layer Perceptron) สำหรับ NSL-KDD

โฟลเดอร์นี้บรรจุโค้ด สถาปัตยกรรมโมเดล และผลการทดลองของ **Deep Feedforward Neural Network (MLP)** บนชุดข้อมูล NSL-KDD สำหรับระบบตรวจจับการบุกรุกเครือข่าย (NIDS)

---

## 1. ชื่อโมเดลและเหตุผลที่เลือก (Rationale)

- **ชื่อโมเดล**: Multi-Layer Perceptron (MLP / Deep Neural Network) พัฒนาด้วย PyTorch
- **บทบาทในโปรเจกต์กลุ่ม**:
  1. **เติมเต็มความหลากหลายของโมเดลในกลุ่ม (Complete 2×2 Matrix)**:
     - สมาชิกคนอื่นเลือก: **XGBoost** (Tree-based Supervised), **Isolation Forest** (Tree-based Anomaly), **Autoencoder** (Neural Network Anomaly)
     - โมเดลนี้ทำหน้าที่เป็นตัวแทนของ **Supervised Deep Learning (Neural Network)** ทำให้การเปรียบเทียบในรายงานกลุ่มครบถ้วนทั้งมิติ Tree vs Neural และ Supervised vs Unsupervised
  2. **ความเหมาะสมกับข้อมูล**: สถาปัตยกรรม MLP ได้ประโยชน์สูงสุดจาก Data Pipeline ที่ทำ `log1p` และ One-Hot Encoding ไว้ใน [`data-pipeline/`](../../data-pipeline/)
  3. **การแก้ปัญหา Class Imbalance ขั้นวิกฤต**: คลาสอย่าง **U2R** และ **R2L** มีตัวอย่างในชุด Train น้อยมาก (U2R มีเพียง 42 ตัวอย่าง หรือ 0.04% ของชุด Train) โครงข่ายประสาทเทียมสามารถใช้ **Smoothed Inverse Class Weighting** ร่วมกับ CrossEntropyLoss เพื่อดึง Recall ของการโจมตีกลุ่มหายากให้สูงขึ้นอย่างมีนัยสำคัญ

---

## 2. ฟีเจอร์และ Preprocessing ที่ใช้

1. **Input Features (160 ฟีเจอร์)**:
   - ฟีเจอร์ตัวเลขดั้งเดิม + ฟีเจอร์วิศวกรรมจาก Data Pipeline (Log-transformed `log1p_*`, Indicator flags, Connection ratios, Error aggregates)
   - One-Hot Encoded Categorical (`protocol_type`, `service`, `flag`)
2. **Data Leakage Prevention**:
   - แยกชุดข้อมูล Train (80%) และ Validation (20%) แบบ **Stratified Split**
   - **`StandardScaler`**: ทำการ `fit` บน Training Split เท่านั้น แล้วนำสเกลเลอร์ตัวเดิมไป `transform` ชุด Validation, `KDDTest+`, และ `KDDTest-21`
3. **Imbalance Handling**:
   - ใช้สูตรถ่วงน้ำหนัก Smoothed Class Weights:
     $$w_c = \sqrt{\frac{N}{K \cdot N_c}}$$
     โดย normalize ให้น้ำหนักเฉลี่ยอยู่ที่ 1.0 เพื่อป้องกันการระเบิดของ Gradient สำหรับคลาส U2R

---

## 3. สถาปัตยกรรมโมเดล (Architecture & Hyperparameters)

```text
Input (160) 
  → Linear(160, 128) → BatchNorm1d → ReLU → Dropout(0.3)
  → Linear(128, 64)  → BatchNorm1d → ReLU → Dropout(0.2)
  → Linear(64, 32)   → BatchNorm1d → ReLU → Dropout(0.15)
  → Linear(32, Num_Classes)
```

- **Optimizer**: AdamW (Learning Rate = `0.001`, Weight Decay = `1e-4`)
- **Scheduler**: `ReduceLROnPlateau` (factor=0.5, patience=3, mode='max')
- **Loss Function**: `nn.CrossEntropyLoss(weight=class_weights)`
- **Batch Size**: 256
- **Epochs**: 25 (พร้อม Early Stopping บันทึกโมเดลที่ให้ค่า Validation Macro F1 สูงสุด)
- **Random Seed**: 42 (กำหนด seed คงที่ทุกจุดเพื่อ Reproducibility)

---

## 4. วิธีรันการทดลอง (How to Run)

ติดตั้งไลบรารีที่จำเป็น:
```bash
pip install -r requirements.txt
```

รันการฝึกโมเดลและประเมินผล (จะรันทั้ง Multiclass และ Binary โดยอัตโนมัติ):
```bash
python train.py --task both --epochs 25 --batch_size 256 --seed 42
```

ไฟล์ผลลัพธ์ที่ได้:
- น้ำหนักโมเดลที่ดีที่สุด: `best_mlp_multiclass.pth`, `best_mlp_binary.pth`
- ผลเมตริกสรุปเป็น JSON: `data-pipeline/sub-dataset/NSL-KDD/output/model_runs/mlp/results_multiclass.json`, `results_binary.json`
- กราฟ Loss & F1 และ Confusion Matrix บันทึกใน `data-pipeline/sub-dataset/NSL-KDD/output/model_runs/mlp/plots/`

---

## 5. ผลการประเมินประสิทธิภาพ (Evaluation Metrics)

### 5.1 การจำแนกประเภท 5 กลุ่มการโจมตี (Multiclass: Normal, DoS, Probe, R2L, U2R)

| Metric | Validation Set | KDDTest+ (ชุดทดสอบมาตรฐาน) | KDDTest-21 (ชุดทดสอบระดับยาก) |
|---|:---:|:---:|:---:|
| **Accuracy** | **99.74%** | **76.37%** | **55.08%** |
| **Balanced Accuracy** | 92.99% | **63.25%** | **55.39%** |
| **Macro F1-Score** | **0.9321** | **0.6440** | **0.5410** |
| **Weighted F1-Score** | 99.74% | **0.7337** | **0.5499** |

#### ประสิทธิภาพรายคลาสบน KDDTest+ (Multiclass)
| Attack Family | Precision | Recall | F1-Score | Support |
|---|:---:|:---:|:---:|:---:|
| **Normal** | 0.9523 | 0.8214 | 0.8820 | 7,460 |
| **DoS** | 0.6839 | **0.9245** | 0.7862 | 9,711 |
| **Probe** | 0.7146 | **0.7261** | 0.7203 | 2,421 |
| **R2L** | 0.6688 | 0.1085 | 0.1867 | 2,885 |
| **U2R** (Rare Class) | **0.7222** | **0.5821** | **0.6446** | 67 |

> 🌟 **จุดเด่นสำคัญ**: ในกลุ่มหายากขั้นวิกฤตอย่าง **U2R** โมเดล MLP สามารถทำ **Recall ได้สูงถึง 58.21%** และ Precision 72.22% (F1 = 0.6446) ซึ่งสูงกว่าโมเดลพื้นฐานทั่วไปที่มักจะได้ Recall ของ U2R ใกล้เคียง 0%

---

### 5.2 การจำแนกแบบ 2 คลาส (Binary: Normal vs Attack)

| Metric | Validation Set | KDDTest+ (ชุดทดสอบมาตรฐาน) | KDDTest-21 (ชุดทดสอบระดับยาก) |
|---|:---:|:---:|:---:|
| **Accuracy** | **99.88%** | **79.64%** | **61.32%** |
| **Balanced Accuracy** | 99.86% | **81.24%** | **63.82%** |
| **Macro F1-Score** | **0.9988** | **0.7964** | **0.5529** |

#### ประสิทธิภาพรายคลาสบน KDDTest+ (Binary)
| Class | Precision | Recall | F1-Score | Support |
|---|:---:|:---:|:---:|:---:|
| **Normal** | 0.6985 | **0.9279** | 0.7970 | 9,711 |
| **Attack** | **0.9274** | 0.6969 | 0.7958 | 12,833 |

---

## 6. ภาพกราฟประกอบการทดลอง (Plots & Visualizations)

- **กราฟการเรียนรู้ (Loss & Macro F1 curves)**:
  - Multiclass: `data-pipeline/sub-dataset/NSL-KDD/output/model_runs/mlp/plots/training_curves_multiclass.png`
  - Binary: `data-pipeline/sub-dataset/NSL-KDD/output/model_runs/mlp/plots/training_curves_binary.png`
- **Confusion Matrix (Normalized)**:
  - `data-pipeline/sub-dataset/NSL-KDD/output/model_runs/mlp/plots/confusion_matrix_kddtestplus_multiclass.png`
  - `data-pipeline/sub-dataset/NSL-KDD/output/model_runs/mlp/plots/confusion_matrix_kddtest-21_multiclass.png`
  - `data-pipeline/sub-dataset/NSL-KDD/output/model_runs/mlp/plots/confusion_matrix_kddtestplus_binary.png`
  - `data-pipeline/sub-dataset/NSL-KDD/output/model_runs/mlp/plots/confusion_matrix_kddtest-21_binary.png`

---

## 7. ข้อสังเกตและข้อจำกัด (Discussion & Limitations)

1. **ผลกระทบจาก Novel Attacks ใน Test Set**:
   - บน Validation Set โมเดลทำ F1 ได้สูงถึง 93-99% แต่บน KDDTest+ ลดลงมาอยู่ที่ ~76-79% และบน KDDTest-21 อยู่ที่ ~55-61%
   - นี่เป็นธรรมชาติของ NSL-KDD ที่ชุด Test มีการโจมตีสายพันธุ์ใหม่ที่ไม่เคยปรากฏใน Train มาก่อน (Out-of-Distribution Attacks) เช่น `mailbomb`, `mscan`, `snmpguess`
2. **ความท้าทายของคลาส R2L**:
   - Recall ของ R2L อยู่ที่ ~10.85% เนื่องจากพฤติกรรมของ R2L มีความคล้ายคลึงกับ Normal Traffic อย่างมาก (เช่น ใช้ bytes ปกติ และผ่าน login)
3. **สิ่งที่สามารถทดลองต่อในอนาคต**:
   - การทดลองใช้ **Focal Loss** เพื่อเพิ่มความสนใจไปยังตัวอย่างที่แยกแยะยากโดยเฉพาะ
   - การทำ **Ensemble (Voting/Stacking)** ร่วมกับ XGBoost ของเพื่อน เพื่อรวมจุดเด่นของ Decision Tree และ Neural Network เข้าด้วยกัน

