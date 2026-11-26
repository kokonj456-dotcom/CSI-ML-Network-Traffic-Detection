# คู่มือเปิดโค้ด Flowwatch ตอนนำเสนอ

เปิดไฟล์ตามคำถามในตาราง แล้วค้นหาชื่อฟังก์ชันด้วย `Ctrl+F` หรือไปที่เลขบรรทัดด้วย `Ctrl+G` เลขบรรทัดอ้างอิงจากโค้ด ณ วันที่จัดทำคู่มือนี้

| ถ้าอาจารย์ถามว่า… | เปิดไฟล์และฟังก์ชัน |
| --- | --- |
| Backend เริ่มงานที่ไหน | [app.py บรรทัด 26](src/app.py#L26) — `create_app` ประกอบบริการ โมเดล ฐานข้อมูล และ routes |
| Scapy จับจาก LAN กับ loopback ยังไง | [live_capture.py บรรทัด 149](src/services/live_capture.py#L149) — `start_capture_adapters` และ [บรรทัด 208](src/services/live_capture.py#L208) — `run` ควบคุมรอบการจับและประมวลผล |
| รวม packet เป็น flow ตรงไหน | [capture/flows.py บรรทัด 34](src/services/capture/flows.py#L34) — `FlowCollector.push` รวมแพ็กเก็ตสองทิศทาง |
| แปลง flow เป็นฟีเจอร์ตรงไหน | [capture/flows.py บรรทัด 110](src/services/capture/flows.py#L110) — `flow_record` สร้างค่าที่โมเดลใช้ รวมถึงบริการ HTTP ที่อ่านพบในแพ็กเก็ต |
| Flow ที่สร้างแล้วเข้าโมเดลและฐานข้อมูลยังไง | [live_capture.py บรรทัด 179](src/services/live_capture.py#L179) — `score_pending_flows` ประเมินเป็นชุด ก่อนเรียกตัวบันทึก MySQL |
| Import PCAP เริ่มตรงไหน | [routes/inference.py บรรทัด 42](src/routes/inference.py#L42) → [controllers/inference.py บรรทัด 106](src/controllers/inference.py#L106) — `upload_capture` → [capture/pcap.py บรรทัด 7](src/services/capture/pcap.py#L7) — `capture_flows` |
| คะแนน Attack, คลาส และ Top factors มาจากไหน | [services/inference.py บรรทัด 52](src/services/inference.py#L52) — `Predictor.predict` ประเมินสองขั้นและคำนวณปัจจัยเมื่อเปิด `explain` |
| CENTRAL Test Demo เข้าระบบอย่างไร | [controllers/inference.py บรรทัด 44](src/controllers/inference.py#L44) — `save_central_test` ใช้ [central_test.py บรรทัด 7](src/services/central_test.py#L7) เตรียม Record ID, คลาสจริง และฟีเจอร์สำหรับประเมินโดยตรง |
| สร้าง Alert ที่ไหน | [mysql_store.py บรรทัด 66](src/db/mysql_store.py#L66) — `save_records` บันทึก flow และ prediction แล้วเพิ่ม Alert เมื่อโมเดลคืน `flagged` |
| หน้า Alerts และ Feedback อ่านหรือแก้ข้อมูลที่ไหน | [alert_queries.py บรรทัด 5](src/db/alert_queries.py#L5) — `alerts` และ `set_alert_status` / [feedback_queries.py บรรทัด 37](src/db/feedback_queries.py#L37) — `report` |
| กด Train แล้วไปไหน | [routes/management.py บรรทัด 23](src/routes/management.py#L23) → [model_training.py บรรทัด 64](src/services/model_training.py#L64) — `start_training_job` และ [บรรทัด 79](src/services/model_training.py#L79) — `run_training_job` |
| เปลี่ยนโมเดล Active หรือหาไฟล์ Backup ตรงไหน | [model_management.py บรรทัด 195](src/services/model_management.py#L195) — `activate` และ [model_registry.py บรรทัด 75](src/services/model_registry.py#L75) — `bundle_path` |

## ลำดับเปิดไฟล์สำหรับเดโม

1. **Live Capture:** เปิด `run` → `FlowCollector.push` → `flow_record` → `score_pending_flows` → `save_records`
2. **CENTRAL Test:** เปิด `save_central_test` → `build_central_test_records` → `Predictor.predict` → `save_records` ทั้งสองเส้นทางใช้โมเดลและกติกาการบันทึก Alert ชุดเดียวกัน
3. **Train & Tune:** เปิด `start_training_job` → `run_training_job` → `activate` ผลเทรนจะเป็น candidate ก่อน ผู้ใช้จึงค่อยเลือกให้เป็น Active จากหน้า Model Management
