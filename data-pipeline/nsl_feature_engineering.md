# Feature Engineering สำหรับ NSL-KDD: คู่มือแบบละเอียด

คู่มือนี้อธิบายขั้นตอนใน nsl_feature_engineering.ipynb ตั้งแต่เหตุผลที่สร้าง feature แต่ละชนิด ตัวอย่างการคำนวณ ไปจนถึงวิธีนำผลลัพธ์ไปใช้กับโมเดล

## 1. เป้าหมายของ Feature Engineering

ข้อมูล cleaned มีตัวแปรที่อธิบาย connection อยู่แล้ว เช่น จำนวน bytes, จำนวน connection, error rate และประเภท service การทำ Feature Engineering จึงมีเป้าหมายเพื่อ:

1. ทำให้โมเดลมองเห็นรูปแบบที่ซ่อนอยู่ในค่าดิบได้ง่ายขึ้น
2. ลดผลของค่าที่มีขนาดใหญ่มากและกระจายเบ้
3. แปลงข้อความประเภทหมวดหมู่ให้เป็นตัวเลข
4. สร้างตัวบ่งชี้เหตุการณ์ที่เกิดขึ้นไม่บ่อย
5. สรุปความสัมพันธ์ระหว่างตัวแปรที่เกี่ยวข้องกัน
6. ป้องกัน target leakage ด้วยการแยกคำตอบออกจาก input

Feature ที่สร้างเป็นตัวเลือกที่มีเหตุผลจากความหมายของข้อมูล ไม่ได้หมายความว่าทุก feature จะทำให้ผลโมเดลดีขึ้น ต้องวัดผลเทียบ baseline ภายหลัง

## 2. Input และ output

Notebook อ่านข้อมูลจาก:

    data-pipeline/output/NSL-KDD/KDDTrain_clean.csv
    data-pipeline/output/NSL-KDD/KDDTest_clean.csv
    data-pipeline/output/NSL-KDD/KDDTest-21_clean.csv

ผลลัพธ์ถูกเขียนลงโฟลเดอร์ใหม่:

    data-pipeline/output/NSL-KDD/feature_engineered/

แต่ละชุดข้อมูลจะได้ไฟล์สองแบบ:

- KDDTrain_features.csv: ตัวแปร input สำหรับโมเดล
- KDDTrain_targets.csv: คำตอบ label, attack_family, is_attack

และมีไฟล์รายงาน:

- feature_schema.csv: ชื่อ feature, ประเภท และคำอธิบาย
- unknown_category_report.csv: หมวดหมู่ใน test ที่ไม่พบใน train
- feature_validation_report.csv: ตรวจจำนวนแถว, missing, infinite และ schema
- feature_engineering_config.json: เก็บกติกาและ path ที่ใช้สร้างข้อมูล

การเก็บ features และ targets แยกกันลดโอกาสที่จะเผลอส่งคำตอบเข้าไปเป็น input ของโมเดล

## 3. แยก feature ออกจาก target

คอลัมน์เหล่านี้เป็นคำตอบ:

| คอลัมน์ | ความหมาย |
|---|---|
| label | ชื่อ traffic หรือ attack รายชนิด เช่น normal, neptune |
| attack_family | กลุ่มใหญ่ เช่น Normal, DoS, Probe, R2L, U2R |
| is_attack | 0 คือ Normal, 1 คือ Attack |

อย่าใส่คอลัมน์ target ลงใน X เพราะโมเดลจะเห็นเฉลย ตัวอย่างการใช้ multiclass:

    X_train = pd.read_csv("KDDTrain_features.csv")
    y_train = pd.read_csv("KDDTrain_targets.csv")["attack_family"]

ถ้าทำ binary classification ให้ใช้:

    y_train = pd.read_csv("KDDTrain_targets.csv")["is_attack"]

สำหรับโปรเจกต์นี้ attack_family เหมาะกับ multiclass มากกว่า label เพราะ KDDTest มี attack บางชนิดที่ไม่มีใน train แต่ยังจัดอยู่ใน family ได้

## 4. Log transformation: log1p

### ปัญหา

ตัวแปรอย่าง src_bytes, dst_bytes, duration, count อาจมีค่าต่ำจำนวนมากและมีหางยาว ค่าขนาดใหญ่มากเพียงไม่กี่แถวทำให้สเกลกว้าง

ตัวอย่างเชิงแนวคิด:

| ค่าเดิม x | log1p(x) โดยประมาณ |
|---:|---:|
| 0 | 0.00 |
| 10 | 2.40 |
| 1,000 | 6.91 |
| 1,000,000 | 13.82 |

สูตรคือ:

    log1p(x) = ln(1 + x)

การบวก 1 ทำให้คำนวณได้แม้ x = 0 และค่าขนาดใหญ่ถูกบีบลงอย่างต่อเนื่อง

Notebook สร้างคอลัมน์ใหม่ เช่น:

    src_bytes = 1,000,000  -> log1p_src_bytes ≈ 13.82
    count = 100            -> log1p_count ≈ 4.62

คอลัมน์เดิมยังอยู่ด้วย เพื่อให้โมเดลหรือการทดลองเลือกใช้ได้ทั้งแบบดิบและแบบแปลง

เหมาะเป็นพิเศษกับ Logistic Regression, SVM และ neural network ที่ไวต่อสเกลของข้อมูล ส่วน tree model มักรับมือค่าตัวเลขขนาดใหญ่ได้ดีอยู่แล้ว จึงควรทดลองเปรียบเทียบ

## 5. Indicator features: มีเหตุการณ์นี้หรือไม่

บางฟีเจอร์เป็นศูนย์เกือบทุกแถว เช่น failed login, root shell และ shell/file activity การเพิ่มตัวบ่งชี้ช่วยให้แยกไม่เกิด กับเกิดขึ้นแล้ว ได้ชัดขึ้น

ตัวอย่าง:

    num_failed_logins = 0  -> has_num_failed_logins = 0
    num_failed_logins = 2  -> has_num_failed_logins = 1

Notebook สร้างตัวบ่งชี้ เช่น:

- has_urgent
- has_num_failed_logins
- has_root_shell
- has_num_root
- has_num_file_creations

และสร้างตัวบ่งชี้รวม:

    has_root_activity = 1
    ถ้า root_shell > 0 หรือ su_attempted > 0 หรือ num_root > 0

    has_file_or_shell_activity = 1
    ถ้า num_file_creations > 0 หรือ num_shells > 0 หรือ num_access_files > 0

ตัวอย่างเหตุผล: แทนที่จะให้โมเดลเรียนรู้เองว่าค่า num_root ที่มากกว่า 0 หมายถึงการทำงานเกี่ยวกับ root ตัว indicator บอกความหมายนี้อย่างชัดเจน

## 6. Byte features: ข้อมูลที่ส่งและรับ

### ปริมาณรวม

    total_bytes = src_bytes + dst_bytes

ตัวอย่าง ถ้าส่ง 800 bytes และรับ 200 bytes:

    total_bytes = 800 + 200 = 1,000
    log1p_total_bytes = ln(1 + 1,000) ≈ 6.91

ค่ารวมสรุป volume ได้ แต่ยังเก็บ src_bytes และ dst_bytes ไว้ เพราะทิศทางการส่ง/รับมีความหมายด้วย

### ความต่างแบบมีทิศทาง

    signed_log_byte_difference
    = sign(src_bytes - dst_bytes) * log1p(abs(src_bytes - dst_bytes))

- ผลบวก: source ส่งข้อมูลมากกว่าที่ได้รับ
- ผลลบ: destination ส่งกลับมามากกว่า
- ใกล้ศูนย์: ปริมาณสองทิศทางใกล้กัน

การใช้ signed log เก็บทิศทางไว้ แต่ลดความต่างระหว่างค่าขนาดใหญ่

### Bytes เทียบกับ duration

    log_byte_duration_ratio = log1p(total_bytes) - log1p(duration)

คุณสมบัติของ log ทำให้ค่านี้เทียบได้กับ log ของอัตราส่วนแบบบวกหนึ่งโดยไม่ต้องหารตรง ๆ จึงลดปัญหาหารด้วยศูนย์

## 7. Connection และ service features

### สัดส่วน connection ที่ใช้ service เดียวกัน

    srv_to_connection_ratio = srv_count / (count + 1)

ตัวอย่าง:

    count = 9, srv_count = 8
    ratio = 8 / (9 + 1) = 0.8

ค่านี้เป็นดัชนีเปรียบเทียบ ไม่ใช่ probability และอาจมากกว่า 1 ได้ เพราะ count กับ srv_count เป็นค่าที่วัดแยกกัน ไม่ได้ถูกจำกัดให้ตัวหนึ่งเป็นส่วนย่อยของอีกตัวหนึ่ง สำหรับข้อมูลชุดนี้พบค่ามากกว่า 1 ได้

บวก 1 ที่ตัวหารเพื่อไม่ให้หารด้วยศูนย์ ผลต่างนี้อาจติดลบได้ถ้า srv_count มากกว่า count

### ส่วนต่างระหว่าง connection กับ service เดียวกัน

    connection_service_gap = count - srv_count

ถ้า count = 30 และ srv_count = 5, gap เท่ากับ 25 ซึ่งอาจช่วยบอกการกระจายของ traffic

## 8. Error-rate aggregates

มี error rate ที่วัดในระดับ connection และระดับ service เช่น:

- serror_rate: SYN error ในกลุ่ม connection
- srv_serror_rate: SYN error ใน service เดียวกัน
- rerror_rate และ srv_rerror_rate: rejection error

Notebook สร้างค่าเฉลี่ย:

    syn_error_mean = (serror_rate + srv_serror_rate) / 2
    reject_error_mean = (rerror_rate + srv_rerror_rate) / 2
    overall_error_rate = ค่าเฉลี่ยของ error rate ทั้งสี่ตัว

ตัวอย่าง ถ้า serror_rate = 0.8 และ srv_serror_rate = 0.6:

    syn_error_mean = (0.8 + 0.6) / 2 = 0.7

อัตราส่วนยังอยู่ในช่วง 0 ถึง 1 เช่นเดิม

## 9. Destination-host features

    host_service_count_ratio = dst_host_srv_count / (dst_host_count + 1)
    host_service_rate_gap = dst_host_same_srv_rate - same_srv_rate
    host_error_mean = ค่าเฉลี่ย error rate สี่ตัวในระดับ destination host

ตัวอย่าง:

    dst_host_srv_count = 100
    dst_host_count = 199
    host_service_count_ratio = 100 / 200 = 0.5

กลุ่มนี้ช่วยเปรียบเทียบพฤติกรรมของ connection ปัจจุบันกับ pattern ที่เห็นใน host ปลายทาง ค่า host_service_count_ratio ก็อาจเกิน 1 ได้เช่นกัน จึงให้มองเป็นดัชนีเปรียบเทียบ ไม่ใช่สัดส่วนที่ถูกจำกัดระหว่าง 0 ถึง 1

## 10. Categorical features และ One-Hot Encoding

ค่าข้อความไม่สามารถป้อนให้โมเดลตัวเลขทั่วไปโดยตรง จึงแปลงเป็นคอลัมน์ 0/1

ตัวอย่าง protocol_type มี tcp, udp, icmp:

| protocol_type | protocol_type=tcp | protocol_type=udp | protocol_type=icmp |
|---|---:|---:|---:|
| tcp | 1 | 0 | 0 |
| udp | 0 | 1 | 0 |
| icmp | 0 | 0 | 1 |

ใช้วิธีเดียวกันกับ service และ flag

Notebook สร้างหมวดหมู่จาก KDDTrain แล้วจัดคอลัมน์ของ KDDTest และ KDDTest-21 ให้ตรงกับ train เพื่อให้ input ของโมเดลมี schema เดียวกันและไม่เรียนรู้ข้อมูลจาก test ตอนเตรียมข้อมูล

ถ้า test มีหมวดหมู่ที่ train ไม่เคยเห็น จะไม่มีคอลัมน์นั้นใน vocabulary ของ train ค่าของกลุ่ม one-hot นั้นจึงเป็นศูนย์ทั้งหมด และจำนวนแถว/หมวดหมู่ดังกล่าวอยู่ใน unknown_category_report.csv

## 11. ทำไมไม่ scale ใน notebook นี้

การ scale ขึ้นกับโมเดล:

- Decision Tree, Random Forest และ Gradient Boosting มักไม่ต้อง scale
- Logistic Regression, SVM, KNN และ neural network มักได้ประโยชน์จาก scaling

ถ้าจะ scale ให้ fit scaler จาก training split เท่านั้น แล้วนำตัวเดิมไป transform validation/test อย่าคำนวณค่าเฉลี่ย, ส่วนเบี่ยงเบนมาตรฐาน หรือ quantile จาก test

แนวทางนี้ทำใน model pipeline ภายหลัง เพื่อไม่ผูกไฟล์ feature กับโมเดลชนิดเดียว

## 12. ป้องกัน data leakage

1. อย่าใส่ label, attack_family หรือ is_attack เข้าใน X
2. อย่าใช้ test คำนวณสถิติสำหรับ encoding, scaling หรือ feature selection
3. ถ้าทดลอง target encoding ต้องทำภายใน cross-validation เท่านั้น
4. แบ่ง validation จาก KDDTrain สำหรับ tuning และใช้ KDDTest ประเมินรอบสุดท้าย
5. ทำ oversampling เฉพาะ train fold หลังแบ่งข้อมูลแล้ว ไม่ทำก่อน split
6. อย่าลบ outlier ทิ้งโดยอัตโนมัติ เพราะ traffic ที่สุดโต่งอาจเป็นสัญญาณของ attack

## 13. วิธีประเมินว่า feature ใหม่ช่วยจริงหรือไม่

เปรียบเทียบชุด feature ทีละกลุ่ม โดยใช้ split และ model เหมือนกัน:

| ชุดทดลอง | สิ่งที่เพิ่มจาก baseline |
|---|---|
| Baseline | numeric ดิบ + One-Hot |
| ทดลอง A | เพิ่ม log1p |
| ทดลอง B | เพิ่ม indicators |
| ทดลอง C | เพิ่ม byte/count ratios |
| ทดลอง D | เพิ่ม error/host aggregates |

สำหรับ class ที่ไม่สมดุล อย่าดู Accuracy อย่างเดียว ควรรายงาน Macro F1, Balanced Accuracy, confusion matrix และ precision/recall แยกตาม attack family โดยเฉพาะ R2L และ U2R

## 14. ใช้ไฟล์ที่สร้างแล้ว

เมื่ออยู่ในโฟลเดอร์ data-pipeline:

    import pandas as pd

    X_train = pd.read_csv(
        "output/NSL-KDD/feature_engineered/KDDTrain_features.csv"
    )
    train_targets = pd.read_csv(
        "output/NSL-KDD/feature_engineered/KDDTrain_targets.csv"
    )
    y_train = train_targets["attack_family"]

    X_test = pd.read_csv(
        "output/NSL-KDD/feature_engineered/KDDTest_features.csv"
    )
    test_targets = pd.read_csv(
        "output/NSL-KDD/feature_engineered/KDDTest_targets.csv"
    )
    y_test = test_targets["attack_family"]

เลือก is_attack เป็น target หากทำ binary classification

ตรวจจำนวนแถวและลำดับแถวให้ตรงกันเสมอ เพราะไฟล์ features และ targets สัมพันธ์กันตามลำดับแถวเดียวกัน



