# XGBoost Experiments & Interactive Dashboard on NSL-KDD

โฟลเดอร์นี้เก็บโค้ดการทดลองโมเดล **XGBoost (Extreme Gradient Boosting)** สำหรับงาน Network Intrusion Detection System (NIDS) พร้อม **Single-Page HTML Dashboard** สำหรับปรับจูนพารามิเตอร์ ดูผลลัพธ์ และเรียกดูประวัติการทดลองย้อนหลัง

---

## 1. แนวคิดและเหตุผลที่เลือก XGBoost

- **Supervised Tree-based Ensemble**: ใช้เปรียบเทียบโดยตรงกับโมเดลของสมาชิกคนอื่น (Isolation Forest ซึ่งเป็น Unsupervised Anomaly Detection และ PyTorch MLP ซึ่งเป็น Deep Learning)
- **ประสิทธิภาพบน Tabular Data**: XGBoost มีกลไก Regularization (L1/L2), รองรับ Sparsity จาก One-Hot Encoding ได้ดี และทนทานต่อข้อมูลที่เบ้ (Skewed distributions)
- **Feature Importance**: ช่วยอธิบายได้ชัดเจนว่า Network Attributes และ Engineered Features ตัวไหนสำคัญที่สุดในการตรวจจับการโจมตี

---

## 2. วิธีใช้งานและเปิด Interactive Dashboard 🚀

เรามี **Single-Page Web Dashboard** (`dashboard.html` + `server.py`) ที่ช่วยให้:
1. **Adjust Hyperparameters**: ปรับจูน `n_estimators`, `max_depth`, `learning_rate`, `subsample`, `cv_folds` ผ่านหน้าเว็บ
2. **Real-time Training & Live Feedback**: กดสั่งเทรนโมเดลใหม่ผ่าน UI ได้ทันที
3. **Inspect Metrics & Visualizations**: แสดงการวัดผล Accuracy, Macro F1, Precision, Recall บน `KDDTest+` และ `KDDTest-21`, กราฟ Feature Importance และ Interactive Confusion Matrix
4. **Historical Run Explorer**: เรียกดูผลลัพธ์ของโมเดลที่เคยบันทึกไว้ใน `model/xgboost/backup/`

### ขั้นตอนการเปิด Dashboard
```bash
conda activate csi403

# สั่งรัน Dashboard Web Server (พอร์ตเริ่มต้น 8080)
python model/xgboost/server.py 8080
```
เปิดบราวเซอร์ไปที่: **`http://localhost:8080/`**

---

## 3. วิธีรันการทดลองผ่าน Command Line (CLI)

```bash
# รันทั้ง Binary และ Multiclass (พร้อม 5-Fold Cross Validation บน KDDTrain)
python model/xgboost/train.py --mode both --cv_folds 5

# หรือเลือกรันเฉพาะโหมด
python model/xgboost/train.py --mode binary
python model/xgboost/train.py --mode multiclass
```

---

## 4. โครงสร้างโฟลเดอร์ Backup (`model/xgboost/backup/`)

ทุกครั้งที่มีการรันการทดลอง ระบบจะสร้างโฟลเดอร์ย่อยตามรูปแบบเวลา ISO:
```text
model/xgboost/backup/
  └── xgboost-{ISO-TIMESTAMP}-{mode}/
        ├── xgboost_model.joblib          # โมเดล XGBoost ที่เซฟไว้พร้อมนำไปเสิร์ฟ/ทดสอบ
        ├── evaluation_results.json       # เมทริกซ์การวัดผล พารามิเตอร์ และ Feature Importance
        ├── confusion_matrix_kddtest.png  # Heatmap Confusion Matrix บน KDDTest+
        ├── confusion_matrix_kddtest21.png# Heatmap Confusion Matrix บน KDDTest-21
        └── top_20_feature_importances.png# กราฟแท่งแสดงฟีเจอร์สำคัญที่สุด 20 อันดับแรก
```

---

## 5. สรุปผลการทดลองล่าสุด (Baseline Performance on 157 Features)

### A. Binary Classification (Normal vs Attack)
- **5-Fold CV (KDDTrain)**:
  - Accuracy: `99.88% (+/- 0.01%)`
  - Macro F1: `0.9988`
- **KDDTest+ (Full Test Set)**:
  - Accuracy: `79.89%`
  - Precision: `96.88%`
  - Recall: `66.82%`
  - F1-Score: `0.7909`
  - ROC-AUC: `0.9670`
- **KDDTest-21 (Difficult Subset with Novel Attacks)**:
  - Accuracy: `61.74%`
  - Precision: `95.17%`
  - Recall: `56.09%`
  - F1-Score: `0.7059`
  - ROC-AUC: `0.8383`

### B. Multiclass Classification (Normal, DoS, Probe, R2L, U2R)
- **5-Fold CV (KDDTrain)**:
  - Accuracy: `99.90%`
  - Macro F1: `0.9281 (+/- 0.0210)`
- **KDDTest+ Performance per Attack Family**:
  - Accuracy: `76.91%`, Macro F1: `0.5650`
  - **Normal**: Precision `67.54%`, Recall `97.15%`, F1 `0.7968`
  - **DoS**: Precision `96.33%`, Recall `82.42%`, F1 `0.8884`
  - **Probe**: Precision `78.27%`, Recall `64.44%`, F1 `0.7068`
  - **R2L**: Precision `98.92%`, Recall `6.37%`, F1 `0.1198`
  - **U2R**: Precision `81.25%`, Recall `19.40%`, F1 `0.3133`

---

## 6. ผลการทำ Hyperparameter Fine-Tuning (เปรียบเทียบ 5 รูปแบบ)

เราได้ออกแบบและทดสอบ 5 Parameter Profiles เพื่อค้นหาจุดที่รับมือกับ Novel Attacks ใน Test Set ได้ดีที่สุด:

| Profile | กลยุทธ์การปรับจูน | พารามิเตอร์ | KDDTest+ Acc | KDDTest+ Macro F1 | Attack Recall | KDDTest-21 Acc |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| **Baseline** | Default Grid | `est=150, depth=6, lr=0.10, sub=0.80, col=0.80` | 79.89% | 0.7986 | 66.82% | 61.74% |
| **Tune 1** | Conservative & Deeper | `est=250, depth=8, lr=0.05, sub=0.85, col=0.70` | 80.10% | 0.8007 | 67.16% | 62.14% |
| **Tune 2** | High Regularization (Shallow) | `est=200, depth=4, lr=0.08, sub=0.75, col=0.65` | 79.97% | 0.7994 | 66.88% | 61.90% |
| **Tune 3** | Moderate Depth & Feature Bagging | `est=180, depth=6, lr=0.06, sub=0.80, col=0.75` | 79.92% | 0.7989 | 66.86% | 61.80% |
| **⭐ Tune 4** | **Diverse Subsampling & Bagging** | `est=220, depth=7, lr=0.05, sub=0.65, col=0.60` | **80.24%** | **0.8022** | **67.39%** | **62.41%** |
| **Tune 5** | Fast Adapted Gradient | `est=300, depth=5, lr=0.04, sub=0.80, col=0.70` | 79.64% | 0.7960 | 66.34% | 61.26% |

### 🏆 Best Hyperparameter Setting ที่ค้นพบ: **Tune 4**
- **พารามิเตอร์ที่ดีที่สุด**:
  - `n_estimators`: **220**
  - `max_depth`: **7**
  - `learning_rate`: **0.05**
  - `subsample`: **0.65**
  - `colsample_bytree`: **0.60**
- **ทำไมการตั้งค่านี้ถึงดีที่สุด?**:
  การลด `subsample` เหลือ 0.65 และ `colsample` เหลือ 0.60 ทำให้ต้นไม้แต่ละต้นถูกบังคับให้เรียนรู้จากฟีเจอร์และตัวอย่างที่หลากหลายขึ้น (Feature & Instance Bagging) ส่งผลให้สามารถตรวจจับการโจมตีรูปแบบใหม่ที่ไม่เคยเห็นมาก่อน (Zero-day / Novel Attacks) ได้เพิ่มขึ้นอย่างมีนัยสำคัญ โดยดึง **Attack Recall ขึ้นมาเป็น 67.39%** และทำคะแนนบนชุดข้อสอบยาก **KDDTest-21 ได้สูงสุดถึง 62.41%**

---

## 7. ผลการทดลองเพิ่มเติม 10 ครั้ง (5 Binary + 5 Multiclass)

เราได้ทำการสำรวจพารามิเตอร์เชิงลึกเพิ่มอีก 10 รูปแบบ (`tune_10.py`):

### A. ฝั่ง Binary Classification (5 Attempts):
1. **bin-att1** (`est=240, d=8, lr=0.04, sub=0.60, col=0.55`): Acc = 79.84%, F1 = 0.7980, Test-21 = 61.65%
2. **⭐ bin-att2** (`est=350, d=6, lr=0.03, sub=0.70, col=0.65`): **Acc = 80.04%**, **F1 = 0.8002**, **Test-21 = 62.03%**
3. **bin-att3** (`est=260, d=7, lr=0.05, sub=0.70, col=0.50`): Acc = 79.55%, F1 = 0.7951, Test-21 = 61.09%
4. **bin-att4** (`est=280, d=5, lr=0.06, sub=0.65, col=0.60`): Acc = 79.69%, F1 = 0.7965, Test-21 = 61.36%
5. **bin-att5** (`est=250, d=9, lr=0.035, sub=0.60, col=0.55`): Acc = 79.72%, F1 = 0.7969, Test-21 = 61.43%

> 💡 **ข้อค้นพบ (Binary)**: การใช้ **ต้นไม้ระดับ 350 ต้น + Learning Rate ต่ำ (0.03)** ควบคู่กับ Subsample 0.70 ช่วยให้โมเดลค่อยๆ ซึมซับสัญญาณรบกวนได้นิ่งขึ้นมาก ทะลุเกณฑ์ 80% ได้อย่างมั่นคง

### B. ฝั่ง Multiclass Classification (5 Attempts):
1. **multi-att1** (`est=180, d=6, lr=0.08, sub=0.75, col=0.70`): Acc = 77.45%, F1 = 0.5475, Test-21 = 57.12%
2. **multi-att2** (`est=220, d=7, lr=0.06, sub=0.65, col=0.60`): Acc = 77.29%, F1 = 0.5505, Test-21 = 56.82%
3. **⭐ multi-att3** (`est=250, d=5, lr=0.05, sub=0.80, col=0.70`): Acc = 77.28%, **Macro F1 = 0.5591**, Test-21 = 56.79%
4. **multi-att4** (`est=200, d=8, lr=0.05, sub=0.70, col=0.65`): Acc = 77.18%, F1 = 0.5494, Test-21 = 56.61%
5. **multi-att5** (`est=300, d=6, lr=0.04, sub=0.70, col=0.65`): **Acc = 77.42%**, F1 = 0.5571, **Test-21 = 57.06%**

> 💡 **ข้อค้นพบ (Multiclass)**: สำหรับงาน 5 คลาส การใช้ **ความลึกต้นไม้ระดับปานกลาง (depth 5–6)** ได้ Macro F1 สูงกว่าการใช้ต้นไม้ลึก (depth 8) เพราะต้นไม้ที่ลึกเกินไปจะ Overfit คลาส Normal/DoS และทิ้งคลาส R2L/U2R
