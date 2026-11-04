# CENTRAL Dataset Pipeline

โฟลเดอร์นี้เก็บขั้นตอนที่ทำกับข้อมูลรวม โดยโค้ดของแต่ละงานอยู่ใน notebook โดยตรงตามรูปแบบของ NSL-KDD และ UNSW-NB15

## Notebook ที่ master runner ใช้

- <code>build_dataset.ipynb</code> อ่าน features/labels/metadata ที่ harmonized จากทั้ง 4 ชุด รวมป้ายกำกับกลาง แบ่ง train/validation/test และเขียนผลลง <code>CENTRAL/output/</code>
- <code>borderline_smote.ipynb</code> ทำ oversampling กับ train และ train_full แยกกัน โดย runner กำหนด split ให้

เรียกจาก project root ด้วย <code>python data-pipeline/build_quad_dataset.py</code>. ตัว runner ไม่บันทึกผลรันกลับเข้า notebook ต้นฉบับ

## Notebook วิเคราะห์ที่รันแยกได้

- <code>eda.ipynb</code> สำรวจ harmonized NSL-KDD และ UNSW-NB15; ผลกราฟ/ตารางอยู่ใน <code>CENTRAL/output/eda/</code>
- <code>analyze_dataset_relationships.ipynb</code> เปรียบเทียบการกระจายของฟีเจอร์จาก train_full; ผลอยู่ใน <code>CENTRAL/output/reports/dataset_relationships/</code>
- <code>feature_engineering.ipynb</code> เป็นทางเลือกสำหรับ StandardScaler/One-Hot ที่ fit จาก train; master runner ไม่ได้เรียก notebook นี้ และ representation ต่างจากทาง SMOTE จึงเก็บผลไว้คนละโฟลเดอร์

ไฟล์ <code>dataset_registry.json</code> และ <code>feature_contract.json</code> เป็นค่ากำกับข้อมูล ไม่ใช่ตัวรัน pipeline. CENTRAL ไม่มีไฟล์ Python ที่ซ้ำกับ implementation ใน notebook แล้ว; ตัวรันและ final audit อยู่ระดับ <code>data-pipeline/</code>.
