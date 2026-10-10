# Model Experiments

ใช้โฟลเดอร์นี้เก็บโค้ดและผลการทดลองโมเดลของสมาชิกแต่ละคน โดยแยกเป็นโฟลเดอร์ย่อยเพื่อไม่ให้ไฟล์ทับกัน

## โครงสร้างที่แนะนำ

```text
model/
  <ชื่อสมาชิกหรือชื่อโมเดล>/
    README.md           # อธิบายแนวคิดและวิธีรัน
    train.py            # หรือ notebook สำหรับฝึกโมเดล
    requirements.txt    # ใส่เฉพาะเมื่อมี dependency เพิ่มจากโปรเจกต์
```

ตัวอย่างชื่อโฟลเดอร์: `model/random-forest/`, `model/xgboost/`, `model/mlp/`

ใน README ของแต่ละโมเดล ควรบันทึก:

- ชื่อโมเดลและเหตุผลที่เลือก
- feature และ preprocessing ที่ใช้
- วิธีรันและ random seed
- metric บน validation/test set เช่น precision, recall, F1 และ confusion matrix
- ข้อจำกัดหรือสิ่งที่ต้องทดลองต่อ

ให้ใช้ข้อมูลที่เตรียมจาก `data-pipeline/` และอย่า commit ชุดข้อมูลดิบ, ไฟล์ output ที่สร้างซ้ำได้, environment ในเครื่อง หรือ secret ต่าง ๆ เพราะรายการเหล่านี้ถูกละเว้นไว้ใน `.gitignore` แล้ว

น้ำหนักโมเดลและ checkpoint ขนาดใหญ่ก็ถูกละเว้นไว้ด้วย ให้เก็บโค้ดฝึกและผลสรุปไว้ใน Git; หากจำเป็นต้องส่ง checkpoint ให้ตกลงวิธีจัดเก็บกับทีมก่อน
