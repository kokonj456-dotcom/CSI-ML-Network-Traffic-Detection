# ผลแก้ harmonization ทั้งสี่ชุด — 8 พฤศจิกายน 2026

Run: `20261108-184157-084453`

**รันจาก raw จนครบและผ่าน audit ในสถานะ diagnostic; ผ่านการทดสอบ 22 กรณี** ข้อมูลชุดใหม่เผยแพร่แล้ว ชุดก่อนหน้าถูกเก็บใน `.pipeline-archives/20261108-184157-084453`

## สิ่งที่แก้

- NSL-KDD: S1/S2/S3 จำนวน 826 แถวเป็น established; http_443 จำนวน 566 แถวอยู่กลุ่ม https_ssl; fallback family เติม source category ให้ตรงกัน
- NSL taxonomy เลือก reference เดียวตาม contract 6: worm 2 แถวเป็น R2L และ httptunnel 133 แถวเป็น U2R โดยเก็บ raw attack names ไว้
- UNSW-NB15: ftp-data จำนวน 5,391 แถวเป็น ftp; เก็บเครื่องหมาย - ผ่าน cleansing เพื่อระบุ unidentified service 141,321 แถวอย่างถูกต้อง; Analysis 2,677 แถวใช้คลาสกลางเดียวกันทั้ง sub-dataset และ CENTRAL
- BoT-IoT: REQ ที่มีข้อมูลขากลับ 4,142 แถวเป็น other แทน no-reply; service ที่ไม่มีพอร์ตต้นทางคง other พร้อม has_service=false
- CIC: ไม่แก้ bytes/packets โดยเดา แต่เก็บ flags/reasons และแยกแถวขัดแย้งออกจากชุดสำหรับโมเดล
- ทุกชุดใช้ shared protocol/service/state rules, per-row availability, boolean types และ canonical labels เดียวกัน พอร์ตผิดรูปแบบ/ทศนิยม/ติดลบไม่ถูกตีความเป็นพอร์ตจริง
- Audit ตรวจ source split, hash ของ input groups, cleaned files, scope/provenance, quarantine และเป้าหมาย SMOTENC จริง; auto-detect ชุด resampled

## Schema ที่ตรวจหลังเผยแพร่

ทั้งสี่ชุดมีชุดชื่อคอลัมน์ตรงกัน: features 22, labels 8 และ metadata 35 คอลัมน์ ตารางเชื่อมด้วย record_id; model inputs ที่ encode แล้วมี 19 ช่อง ส่วน labels/metadata ไม่เข้า X

## จำนวนแถว

| แหล่ง | ทั้งหมดใน harmonized | เข้า CENTRAL | Quarantine |
|---|---:|---:|---:|
| NSL-KDD | 148,517 | 148,517 | 0 |
| UNSW-NB15 | 257,673 | 257,673 | 0 |
| CIC-IDS2017 | 170,657 | 145,634 | 25,023 |
| BoT-IoT | 170,657 | 170,657 | 0 |

**Source harmonized ยังเก็บทั้งหมด 747,504 แถว; CENTRAL ใช้ 722,481 แถว** มี CIC source-test 2,941 แถวอยู่ใน quarantine จึงเหลือ test 141,935 แถว ต้องเปิดเผยการตัดออกนี้เมื่อรายงานคะแนน และห้ามอ้างว่าเป็น test population ทางการที่ไม่ได้เปลี่ยนแปลง

| Split | Rows |
|---|---:|
| train | 426,445 |
| train_full | 580,546 |
| validation | 154,101 |
| test | 141,935 |
| train_smote | 449,861 |
| train_full_smote | 599,967 |

Validation แบ่งตามกลุ่มฟีเจอร์ที่เหมือนกัน จึงไม่จำเป็นต้องได้ 20% ของแถวพอดี; train_full คือ train รวม validation ไม่ใช่ชุดทดสอบอิสระ

## การตรวจหลังเผยแพร่

- เปรียบเทียบ raw กับ source harmonized ทุกแถว: duration/bytes/packet counts ที่มีอยู่ต่างกัน 0 ค่า และ binary labels ต่างกัน 0 แถวในทั้งสี่ชุด
- ตรวจ service=- ของ UNSW หลัง cleansing ถึง metadata: 141,321 แถวถูกระบุว่าไม่ทราบบริการครบ
- ตรวจ code fingerprint ตรงกับ build manifest และ audit ตรวจทั้ง baseline/resampled แล้ว
- `python -m unittest discover -s data-pipeline/tests -v`: 22 tests ผ่าน รวม harmonization, quarantine, no test leakage, fake groups, provenance, cleaned artifacts และ SMOTENC target reporting
- `git -c core.whitespace=cr-at-eol diff --check`: ผ่าน

## หลักฐาน

- `CENTRAL/output/reports/harmonization_validation.json`
- `CENTRAL/output/reports/audit.json`
- `CENTRAL/output/reports/quarantine_summary.csv`
- `sub-dataset/CIC-IDS2017/output/harmonized/quarantine/` เก็บทั้ง features/labels/metadata พร้อม record IDs และเหตุผล
- `HARMONIZATION_POLICY.md` และ `CENTRAL/feature_contract.json` อธิบายกฎและ reference ของ taxonomy
- `.pipeline-runs/20261108-184157-084453/pipeline.log` เป็น log รอบที่ผ่าน

## ข้อจำกัดที่ไม่สร้างข้อมูลขึ้นมาแก้

1. CIC raw ที่มีอยู่เป็นข้อมูลจำลอง; BoT ยังมี provenance ไม่ครบ จึงผ่านแบบ diagnostic เท่านั้น
2. BoT ไม่มีพอร์ต/service ใน raw จึงไม่สามารถกู้บริการจริงจากการเปลี่ยนชื่อคอลัมน์ได้ ค่า other และ availability=false แสดงข้อจำกัดนี้; service - ของ UNSW ก็ถูกแยกว่าระบุบริการไม่ได้
3. Port hints ไม่ใช่การยืนยัน application protocol และ byte counters จากแต่ละ extractor ยังต้องมีนิยามอ้างอิงก่อนอ้างว่าเทียบทางกายภาพได้ครบ
4. Test ยังมี feature vectors ที่ซ้ำกับ training; ต้องประเมิน sensitivity และแยก source การตรวจนี้ไม่ได้ฝึกโมเดลหรืออัปเดต dashboard เดิม

ต้อง rebuild/retrain โมเดลเดิมก่อนเปรียบเทียบคะแนน เพราะ mapping, taxonomy, eligibility และจำนวนแถวเปลี่ยนแล้ว

ไฟล์ output ทดลองจากรอบก่อนยังเก็บอยู่ ระบบนโยบายบล็อกคำสั่งลบ generated outputs เก่า จึงไม่ได้ลบไฟล์เหล่านั้น การ publish รอบนี้สำเร็จโดยเก็บ archive ไว้
