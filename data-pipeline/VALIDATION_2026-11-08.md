# ผลตรวจ pipeline หลังแก้ไข — 8 พฤศจิกายน 2026

รอบที่ตรวจ: `20261108-171332-637616` — เริ่มจาก raw ในเครื่อง โดยไม่ใช้ output เก่า และไม่ดาวน์โหลดข้อมูลมาแทนต้นฉบับ

**ผล: รันครบทุกขั้นและ audit ผ่านในสถานะ `diagnostic`** ผลใหม่อยู่ที่ `CENTRAL/output` ส่วนชุดก่อนหน้าอยู่ที่ `../.pipeline-archives/20261108-171332-637616`

คำสั่งที่รัน:

```powershell
python data-pipeline/build_quad_dataset.py --allow-unverified-data --resampling smotenc
```

## ผลแต่ละขั้น

- Cleansing และ harmonization ทั้ง NSL-KDD, UNSW-NB15, CIC-IDS2017, BoT-IoT: ผ่าน
- CENTRAL mapping และแบ่งชุด: ผ่าน
- Feature engineering: 19 คอลัมน์ ใช้ scaler/encoder ชุดเดียวที่ fit จาก train
- SMOTENC ทั้ง train และ train_full: ผ่าน; categorical ไม่ถูก interpolate แบบ one-hot
- Audit: ผ่าน รวมการเทียบกับตารางต้นทาง, hash, labels, ID, split, preprocessing และ synthetic rows
- หลังนำผลไปแทนชุดเดิม: fingerprint โค้ดตรงกับ manifest และตรวจพบ archive ชุดเดิม

| ชุด | จำนวนแถว |
|---|---:|
| train | 496,287 |
| train_full | 602,628 |
| validation | 106,341 |
| test | 144,876 |
| train_smote | 519,768 |
| train_full_smote | 622,049 |

`train_full` คือ train รวม validation; ห้ามใช้เป็นชุดทดสอบอิสระ การแบ่ง validation ยึดกลุ่มฟีเจอร์ที่เหมือนกัน จึงไม่จำเป็นต้องได้จำนวนแถว 20% พอดี

## จุดที่แก้

- แก้พาธ NSL/UNSW, การ import display และ UTF-8 ของตัวรัน
- เพิ่ม mapping ตามแหล่งข้อมูล และปฏิเสธ label ที่ไม่รู้จัก แทนการโยนเข้า Malware
- แก้ชนิด label_raw/ID ให้คงเป็นข้อความเมื่อรวมข้อมูลและอ่าน CSV กลับ
- แก้ manifest ของ CIC/BoT ให้ hash raw จริง และตรวจ code/config/table dependencies ก่อนใช้ข้อมูล
- สร้างทุกขั้นใน run ใหม่ ตรวจผ่านก่อน publish และมี rollback/เก็บ archive
- แก้ BoT ที่ไม่มี dport ให้ระบุ service ไม่พร้อมและใช้ other เฉพาะโหมด diagnostic
- หยุดการเติมศูนย์/clip ตัวเลขที่ผิดโดยเงียบ ๆ
- รวม preprocessing ให้ตรงกันทุก split และ SMOTENC; synthetic IDs แยก split และ sample_weight เท่ากับ 1
- ดาวน์โหลด online ล้มเหลวแล้วหยุด; สร้าง demo ได้เฉพาะระบุ emulate พร้อมบันทึก provenance
- แบ่ง validation ด้วยกลุ่ม input ที่เหมือนกันโดยไม่อ่าน label หรือ test เพื่อเลือกกลุ่ม
- Audit เปลี่ยนเป็น fail จริงเมื่อข้อมูลผิด พร้อม JSON report

## สิ่งที่ยังเหลือเป็นข้อจำกัดของข้อมูล

1. **CIC ปัจจุบันตรวจพบรูปแบบข้อมูลจำลอง (`emulate`); BoT ยังไม่มีหลักฐาน source provenance ครบ (`unverified`)** จึงยังใช้รอบนี้อ้างว่าเป็น benchmark ทางการทั้งสี่ชุดไม่ได้ โหมดปกติหยุดก่อนรันหากไม่ยอมรับ diagnostic อย่างชัดเจน
2. **BoT ขาด dport/service ทั้ง 170,657 แถว** ไม่สร้างค่าพอร์ตขึ้นเอง หากต้องการ profile ที่มี measured fields ครบต้องจัดหา raw ที่เก็บพอร์ตจริง หรือออกแบบ/ประเมิน profile ที่ตัด service ออกทั้งทุกแหล่ง
3. **test มีฟีเจอร์เหมือน train**: 53,383 แถวเมื่อเทียบ input กลาง 6 ช่อง; ไม่ใช่หลักฐานว่าเป็นเหตุการณ์เดียวกัน เก็บ source test ไว้และควรรายงานผล sensitivity/แยก source
4. **มี 1,317 feature vectors ที่สัมพันธ์กับหลายคลาส** หลัง mapping ถูกแก้แล้ว ควรตรวจนิยาม/ข้อมูลที่หายไปจากการลดฟีเจอร์ และให้อาจารย์ทบทวน taxonomy; ไม่ลบแถวโดยไม่มีหลักฐาน

**Train/validation ไม่มี input vectors ซ้ำข้ามกลุ่ม: 0 แถว**

## การทดสอบ

`python -m unittest discover -s data-pipeline/tests -v` — **ผ่าน 9 tests** ครอบคลุม unknown labels, binary consistency, missing/negative/infinite inputs, stale raw, categorical resampling, demo provenance, online failure, audit ทั้งกระบวนการ และ rollback เมื่อ publish ล้มเหลว รวม regression ของ numeric source labels และ test-only changes ที่ต้องไม่เปลี่ยน validation assignment

`git -c core.whitespace=cr-at-eol diff --check` — ผ่าน (รองรับไฟล์ CRLF ที่มีอยู่ใน repository)

## หลักฐานและการใช้งานต่อ

- `CENTRAL/output/reports/audit.json`
- `CENTRAL/output/reports/label_mapping.csv`
- `CENTRAL/output/reports/overlap.json`
- `CENTRAL/output/data_sources.json`
- `CENTRAL/output/build_manifest.json`
- `CENTRAL/output/RUN_PROVENANCE.json`
- Log: `../.pipeline-runs/20261108-171332-637616/pipeline.log`

Schema รุ่น 5 เปลี่ยน preprocessing จากผลเก่า ต้องฝึกโมเดลใหม่ด้วย `CENTRAL/output/feature_engineering/preprocessor.joblib` ของรอบนี้ ก่อนนำคะแนนไปเทียบหรือใช้งาน โมเดลและ dashboard เดิมไม่ได้ถูกฝึกใหม่ในการตรวจ data pipeline นี้

Environment: Python 3.14.4, pandas 3.0.6, numpy 2.5.3, scikit-learn 1.9.1, imbalanced-learn 0.14.2
