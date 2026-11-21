# Wireshark Live Defense Monitor // AI Intrusion Detection System

ระบบจำลองการสตรีมทราฟฟิกเครือข่ายแบบเรียลไทม์ (Live Traffic Stream Playback) เชื่อมต่อกับเว็บแดชบอร์ดสไตล์ **Wireshark Network Security Monitor** ขับเคลื่อนด้วยโมเดลโปรดักชัน **XGBoost M9 (CENTRAL-FINAL 5.04M Rows Two-Stage Architecture)**

---

## 1. Quick Start (วิธีรันระบบใน 1 คำสั่ง)

เปิด Terminal ในโฟลเดอร์ root ของโปรเจกต์ แล้วรันคำสั่ง:

```bash
./live_traffic_monitor/run_live_monitor.sh
```

สคริปต์จะเริ่มทำงานบนพอร์ต **8088** และเปิดเบราว์เซอร์ไปยัง `http://localhost:8088` โดยอัตโนมัติ

หรือสั่งรันโดยตรงผ่าน Python:
```bash
cd live_traffic_monitor/backend
/opt/miniconda3/envs/csi403/bin/python server.py
```

---

## 2. ฟังก์ชันและคุณสมบัติเด่นสำหรับการนำเสนอ (Presentation Highlights)

1. **Wireshark Dark Aesthetic (#112f8d, #097c5c, #f1f5fa)**:
   - ออกแบบอินเตอร์เฟซเสมือนจริงตามสไตล์ Wireshark และโปรแกรมดักจับแพ็กเก็ตเครือข่ายระดับสากล
   - ไฮไลต์แถวที่เป็น Attack ด้วยสีแดงอ่อนทันที เพื่อให้เห็นความผิดปกติอย่างชัดเจน
2. **Two-Pane Wireshark Packet Inspector (ครึ่งล่างของจอ)**:
   - คลิกที่แถวใดๆ บนตาราง เพื่อขยายดูรายละเอียดเชิงลึก 5 ระดับ:
     - **Frame Overview**: ความยาวแพ็กเก็ตบนสายสัญญาณ, เวลา, โปรโตคอล
     - **IPv4 Layer**: Source IP, Destination IP, TTL
     - **Transport Layer**: TCP/UDP, พอร์ตต้นทาง/ปลายทาง, สถานะการเชื่อมต่อ (State)
     - **Flow Behavioral Physics (19 Features)**: ตารางสรุป 19 ฟีเจอร์พฤติกรรมฟิสิกส์
     - **AI Intrusion Detection Engine (Model M9)**: แสดงผล Stage 1 Binary (Score vs 0.45 Threshold) และ Stage 2 MITRE ATT&CK Classification พร้อม Confidence % และค่า Inference Latency (~1.1 ms)
3. **Interactive Attack Injection Toolbar (ปุ่มลัดยิงการโจมตีจำลอง)**:
   - `[Normal Burst (x15)]`: ยิงทราฟฟิกปกติเข้าสู่ระบบ
   - `[PortScan (Recon)]`: ยิงการสแกนพอร์ตเครือข่าย (Class 2: Reconnaissance)
   - `[SSH Brute Force]`: ยิงการเดารหัสผ่าน SSH (Class 4: Credential Abuse)
   - `[SYN Flood (DoS)]`: ยิงคลื่นทราฟฟิกถล่มเซิร์ฟเวอร์ (Class 1: Denial of Service)
   - `[Web Exploits (SQLi)]`: ยิงช่องโหว่เว็บและเจาะระบบ (Class 3: Exploits)
   - `[Botnet / C2]`: ยิงทราฟฟิกติดต่อเครื่องควบคุมมัลแวร์ (Class 5: Botnet)
4. **Auto-Play 3-Minute Live Scenario (เนื้อเรื่องจำลองอัตโนมัติ)**:
   - กดปุ่ม `Start 3-Min Live Scenario` เพื่อให้ระบบดำเนินเนื้อเรื่อง 6 เฟสอย่างราบรื่นระหว่างยืนพรีเซนต์:
     - เฟส 1 (00:00 - 00:30): ทราฟฟิกปกติประจำวัน (สีเขียวสม่ำเสมอ)
     - เฟส 2 (00:30 - 01:00): เริ่มตรวจพบ Reconnaissance & Port Scanning จากแฮกเกอร์ภายนอก (Alert สีส้ม)
     - เฟส 3 (01:00 - 01:30): แฮกเกอร์พยายามเจาะ SSH Brute Force เข้าเครื่องเซิร์ฟเวอร์
     - เฟส 4 (01:30 - 02:10): ทราฟฟิก SYN Flood ถล่มเซิร์ฟเวอร์อย่างหนัก กราฟสีแดงพุ่งสูง
     - เฟส 5 (02:10 - 02:40): แฮกเกอร์ฉวยโอกาสยิง Web Application Exploits
     - เฟส 6 (02:40 - 03:00): ตรวจพบ Botnet C2 Beaconing และโมเดลจำแนกประเภทได้สำเร็จ
5. **Dual Mode (WebSocket Live + Standalone Offline Mode)**:
   - หากเปิดเซิร์ฟเวอร์ Python ไม่ได้ หรือมีปัญหาเรื่องพอร์ตในวันพรีเซนต์ สามารถคลิกปุ่ม `Offline Mode` ที่มุมขวาบน ระบบจะสลับไปใช้ Client-Side Mock Replay บนเบราว์เซอร์ได้ 100% โดยไม่ต้องพึ่งพาเซิร์ฟเวอร์

---

## 3. Real PCAP Replay (การยิงทราฟฟิกแพ็กเก็ตของจริงจากไฟล์ .pcap)

ระบบได้ดาวน์โหลดและบรรจุตัวอย่างไฟล์จับแพ็กเก็ตของจริง (Authentic PCAP Benchmarks จาก Practical Packet Analysis) ไว้ใน `data/pcaps/`:
- `portscan.pcap` (Nmap PortScan ของจริง ตรวจจับเป็น Class 2: Reconnaissance)
- `dosattack.pcap` (TCP SYN Flood DoS โจมตีของจริง)
- `ftp-crack.pcap` (Hydra FTP Password Brute Force ของจริง 714 โฟลว์)
- `blaster.pcap` (Blaster Worm มัลแวร์ของจริง)
- `http_normal.pcap` (การเปิดเว็บเบราว์เซอร์ปกติ)
- `dns_normal.pcap` (การส่ง DNS Queries ปกติ)

### วิธีการรัน PCAP Replay:
1. **ผ่าน Web Dashboard โดยตรง (แนะนำ)**:
   คลิกที่แถบ **Real PCAP Replay** ด้านบนตาราง เพื่อสั่งให้เซิร์ฟเวอร์อ่านไฟล์ PCAP แล้วสตรีมเข้าหน้าจอทันที
2. **ผ่านคำสั่ง CLI Terminal**:
   ```bash
   # สตรีม PCAP เจาะจงไฟล์
   /opt/miniconda3/envs/csi403/bin/python live_traffic_monitor/backend/pcap_streamer.py --pcap portscan.pcap --speed 2.0

   # สตรีมทุก PCAP ต่อเนื่องกัน (เหมาะสำหรับพรีเซนต์สด)
   /opt/miniconda3/envs/csi403/bin/python live_traffic_monitor/backend/pcap_streamer.py --all --speed 2.0
   ```

---

## 4. สถาปัตยกรรมและโครงสร้างไฟล์

```text
live_traffic_monitor/
├── backend/
│   ├── server.py              # FastAPI server + WebSocket endpoint (/ws/traffic) + REST API
│   ├── traffic_generator.py   # เอนจินสตรีมทราฟฟิกและจัดการคิวการยิงการโจมตี
│   ├── pcap_streamer.py       # เอนจินอ่านและ Replay ไฟล์ .pcap เข้าสู่โมเดล M9
│   └── model_runtime.py       # รันโมเดล Two-Stage XGBoost (Stage 1 Binary + Stage 2 Multiclass)
├── frontend/
│   ├── index.html             # แดชบอร์ดสไตล์ Wireshark (Chart.js + Tailwind CSS)
│   ├── app.js                 # เอนจินควบคุม WebSocket, ตาราง, กราฟ, PCAP Replay
│   └── styles.css             # ธีมสีหลัก: #112f8d, #097c5c, #f1f5fa, #0a1128
├── data/
│   ├── pcaps/                 # ไฟล์แพ็กเก็ตของจริง (.pcap) 7 ไฟล์
│   └── sample_flows.json      # 1,800 ตัวอย่างทราฟฟิกเครือข่ายของจริง (300 ต่อคลาส)
├── run_live_monitor.sh        # สคริปต์เปิดระบบและเปิดเบราว์เซอร์ใน 1 คำสั่ง
└── README.md
```

---

## 5. API Endpoints

- `GET /`: เปิดหน้าเว็บ Web Dashboard
- `GET /api/status`: ตรวจสอบสถานะการทำงาน, อัตราโฟลว์, สถิติ, และเฟสปัจจุบันของ Scenario
- `GET /api/pcaps`: รายชื่อไฟล์ PCAP ของจริงที่มีอยู่ในระบบ
- `POST /api/replay_pcap/{pcap_name}`: สั่ง Replay ไฟล์ PCAP เข้าสู่สตรีมแบบเรียลไทม์
- `POST /api/control`: สั่งการเล่นทราฟฟิก (`play`, `pause`, `speed`, `scenario_start`, `reset`)
- `POST /api/inject/{attack_type}`: ยิงการโจมตีจำลอง (`portscan`, `bruteforce`, `dos`, `exploit`, `botnet`, `normal`)
- `WS /ws/traffic`: WebSocket แบบสองทิศทาง ส่งสตรีมแพ็กเก็ตแบบเรียลไทม์
