# คู่มือเปิดโค้ด Flowwatch ตอนนำเสนอ

เปิดไฟล์ตามคำถามในตาราง แล้วค้นหาชื่อฟังก์ชันด้วย `Ctrl+F`

## อ่าน Backend จากหนึ่ง flow

1. **รับข้อมูล** — Live Capture อ่านแพ็กเก็ตที่เห็น ส่วน Import PCAP อ่านแพ็กเก็ตจากไฟล์
2. **รวมแพ็กเก็ต** — แพ็กเก็ตที่วิ่งไปมาระหว่างคู่ปลายทางจะถูกรวมเป็น flow ระบบสรุปข้อมูลอย่างเวลาและจำนวนไบต์เพื่อส่งให้โมเดล
3. **ทำนาย** — โมเดลให้คะแนนความเป็น attack แล้วระบบเทียบคะแนนกับ threshold หากถูก flag จะแสดงข้อมูลคลาสจากโมเดลขั้นที่สอง
4. **บันทึก** — MySQL เก็บ flow และผลทำนาย แล้วสร้าง alert เมื่อผลระบุว่า flow ถูก flag

ในโค้ด `routes` คือประตูรับคำขอจากหน้าเว็บ `controllers` จัดลำดับงานตามคำขอ `services` ทำงานอย่างจับแพ็กเก็ตหรือทำนาย ส่วน `db` อ่านและบันทึกข้อมูล

| ถ้าอาจารย์ถามว่า… | เปิดไฟล์และฟังก์ชัน |
| --- | --- |
| Backend เริ่มงานที่ไหน | [app.py](src/app.py) — `create_app` ประกอบบริการ โมเดล ฐานข้อมูล และ routes |
| Scapy จับจาก LAN กับ loopback ยังไง | [live_capture.py](src/services/live_capture.py) — `start_capture_adapters` และ [live_capture.py](src/services/live_capture.py) — `run` ควบคุมรอบการจับและประมวลผล |
| รวม packet เป็น flow ตรงไหน | [capture/flows.py](src/services/capture/flows.py) — `FlowCollector.push` รวมแพ็กเก็ตสองทิศทาง |
| แปลง flow เป็นฟีเจอร์ตรงไหน | [capture/flows.py](src/services/capture/flows.py) — `flow_record` สร้างค่าที่โมเดลใช้ รวมถึงบริการ HTTP ที่อ่านพบในแพ็กเก็ต |
| Flow ที่สร้างแล้วเข้าโมเดลและฐานข้อมูลยังไง | [live_capture.py](src/services/live_capture.py) — `score_pending_flows` ประเมินเป็นชุด ก่อนเรียกตัวบันทึก MySQL |
| Import PCAP เริ่มตรงไหน | [routes/captures.py](src/routes/captures.py) → [controllers/captures.py](src/controllers/captures.py) — `upload_capture` → [capture/pcap.py](src/services/capture/pcap.py) — `capture_flows` |
| คะแนน Attack, คลาส และ Top factors มาจากไหน | [services/inference.py](src/services/inference.py) — `Predictor.predict` ประเมินสองขั้นและคำนวณปัจจัยเมื่อเปิด `explain` |
| CENTRAL Test Demo เข้าระบบอย่างไร | [controllers/inference.py](src/controllers/inference.py) — `save_central_test` ใช้ [central_test.py](src/services/central_test.py) เตรียม Record ID, คลาสจริง และฟีเจอร์สำหรับประเมินโดยตรง |
| API อ่าน Flow และเปลี่ยนสถานะ Alert ตรงไหน | [routes/traffic.py](src/routes/traffic.py) → [controllers/traffic.py](src/controllers/traffic.py) ดู `traffic_flows` และ `update_alert` |
| สร้าง Alert ที่ไหน | [mysql_store.py](src/db/mysql_store.py) — `save_records` บันทึก flow และ prediction แล้วเพิ่ม Alert เมื่อโมเดลคืน `flagged` |
| หน้า Alerts และ Feedback อ่านหรือแก้ข้อมูลที่ไหน | [alert_queries.py](src/db/alert_queries.py) — `alerts` และ `set_alert_status` / [feedback_queries.py](src/db/feedback_queries.py) — `report` |
| กด Train แล้วไปไหน | [routes/management.py](src/routes/management.py) → [model_training.py](src/services/model_training.py) — `start_training_job` และ [model_training.py](src/services/model_training.py) — `run_training_job` |
| เปลี่ยนโมเดล Active หรือหาไฟล์ Backup ตรงไหน | [model_management.py](src/services/model_management.py) — `activate` และ [model_registry.py](src/services/model_registry.py) — `bundle_path` |

## จุดเปิดโค้ดฝั่งหน้าเว็บ

| ถ้าอาจารย์ถามว่า… | เปิดไฟล์และฟังก์ชัน |
| --- | --- |
| โหลดข้อมูลเกิน 250 รายการอย่างไร | [loadTraffic.js](../frontend/src/features/traffic/loadTraffic.js) ดู `refreshTraffic` และ `fetchAllTrafficPages` เพื่อเห็นการไล่ cursor |
| แปลงผลจาก API เป็นข้อมูลบนหน้าเว็บที่ไหน | [mapFlow.js](../frontend/src/features/traffic/mapFlow.js) ดู `dashboardFlow` |
| ค้นหา IP และกรองช่วงเวลาอย่างไร | [filterFlows.js](../frontend/src/features/traffic/filterFlows.js) ดู `filtered` |
| ตารางเลือกแถวที่จะแสดงบนแต่ละหน้าอย่างไร | [table.js](../frontend/src/features/traffic/table.js) ดู `renderTable` |
| รวม Alert เป็นกลุ่มและจัดการหลายรายการอย่างไร | [groupedView.js](../frontend/src/features/alerts/groupedView.js) ดู `groupedAlerts` แล้วเปิด [selection.js](../frontend/src/features/alerts/selection.js) เพื่อดู `bulkAlertAction` |
| ตัวเลขใน Live Monitor กับ Navbar คำนวณจากอะไร | [monitor.js](../frontend/src/features/monitor.js) ดู `renderMetrics` และ [layout.js](../frontend/src/core/layout.js) ดู `openCount` |
| เปิดรายละเอียด Flow หรือประวัติ IP อย่างไร | [drawer.js](../frontend/src/features/inspector/drawer.js) ดู `showInspector` แล้วตามไปที่ [flowDetails.js](../frontend/src/features/inspector/flowDetails.js) หรือ [ipHistory.js](../frontend/src/features/inspector/ipHistory.js) |

## ลำดับเปิดไฟล์สำหรับเดโม

1. **Live Capture:** เปิด `run` → `FlowCollector.push` → `flow_record` → `score_pending_flows` → `save_records`
2. **CENTRAL Test:** เปิด `save_central_test` → `build_central_test_records` → `Predictor.predict` → `save_records` ทั้งสองเส้นทางใช้โมเดลและกติกาการบันทึก Alert ชุดเดียวกัน
3. **Train & Tune:** เปิด `start_training_job` → `run_training_job` → `activate` ผลเทรนจะเป็น candidate ก่อน ผู้ใช้จึงค่อยเลือกให้เป็น Active จากหน้า Model Management
