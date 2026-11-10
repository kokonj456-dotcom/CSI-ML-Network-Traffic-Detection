# ตารางเปรียบเทียบผลการฝึกโมเดล Autoencoder

การทดลองเปรียบเทียบกลยุทธ์การจัดการ Imbalance (SMOTENC & Sample Weighting) บนชุดทดสอบกลาง Quad-Dataset (144,876 flows)

| วิธีฝึก | Accuracy | Precision | Recall | F1-score |
| :--- | :---: | :---: | :---: | :---: |
| **ไม่ทำ SMOTE ไม่เพิ่ม weight** | 79.67% | 83.79% | 79.50% | 81.59% |
| **ไม่ทำ SMOTE + weight R2L** | 72.81% | 78.10% | 72.28% | 75.08% |
| **ทำ SMOTENC** | 78.91% | 83.80% | 77.83% | 80.71% |
| **ทำ SMOTENC + weight R2L** | 74.15% | 81.91% | 69.79% | 75.37% |

### รายละเอียดเพิ่มเติมเชิงลึก (Detailed Metrics Breakdown)
| วิธีฝึก | R2L Detection Rate (Recall) | False Positive Rate (FPR) | Alert Threshold |
| :--- | :---: | :---: | :---: |
| **ไม่ทำ SMOTE ไม่เพิ่ม weight** | 84.26% | 20.12% | 0.031717 (82.5%) |
| **ไม่ทำ SMOTE + weight R2L** | 62.11% | 26.50% | 0.025304 (80.0%) |
| **ทำ SMOTENC** | 60.42% | 19.67% | 0.023319 (83.0%) |
| **ทำ SMOTENC + weight R2L** | 87.63% | 20.15% | 0.113126 (82.0%) |
