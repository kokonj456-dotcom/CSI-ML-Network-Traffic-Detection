# CENTRAL Dataset Pipeline

Master runner ใช้ `build_dataset.py` รวม harmonized data สี่ชุด จากนั้น execute `borderline_smote.ipynb` สองรอบ โดยกำหนด `SMOTE_SPLIT=train_full` และ `train`; algorithm อยู่ใน notebook นี้โดยตรง

`build_dataset.ipynb` เป็น prototype เก่าสำหรับ NSL-KDD/UNSW-NB15 สองชุดและผลไม่เทียบเท่า builder ปัจจุบัน ส่วน `feature_engineering.ipynb` มี preprocessing จริงแต่ยังไม่อยู่ใน runner และ path `common/` ยังใช้ไม่ได้ใน checkout นี้

ดู [`../PIPELINE_FILE_GUIDE.md`](../PIPELINE_FILE_GUIDE.md) สำหรับรายละเอียด
