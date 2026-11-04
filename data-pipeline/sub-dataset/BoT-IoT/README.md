# BoT-IoT Pipeline

Pipeline สำหรับดาวน์โหลด ทำความสะอาด (Cleansing) และประสานโครงสร้าง (Harmonization) ชุดข้อมูล **BoT-IoT (UNSW Canberra Cyber Range Lab)** จากทราฟฟิกเซ็นเซอร์เครือข่ายอินเทอร์เน็ตของสรรพสิ่ง (IoT) เพื่อเชื่อมโยงเข้าสู่ชุดข้อมูลรวมศูนย์ **CENTRAL Dataset**

---

## 1. วิธีการทำงาน (How It Works)

```mermaid
flowchart TD
    A["UNSW BoT-IoT 5% Online Mirrors (Part 1 + Part 4: 868k Real Flows)"] -->|download.py --source online| B["raw/ (BoT_IoT_training-set.csv / testing-set.csv)"]
    B -->|cleansing.ipynb| C["output/cleansing/ (Deduplication, Audit, SHA-256 Manifest)"]
    C -->|harmonization.ipynb| D["output/harmonized/ (features.csv, labels.csv, metadata.csv)"]
    D --> E["CENTRAL Dataset Integration (/data-pipeline/CENTRAL)"]
```

1. **Automated Online Mirror Ingestion**: `download.py` ดึงข้อมูลทราฟฟิกจริงของ BoT-IoT จาก Mirror ทางการ (Part 1 และ Part 4 รวมขนาดบีบอัด ~30 MB) ครอบคลุมทราฟฟิกจริง 868,522 โฟลว์ครบทุกหมวด:
   * **DDoS & DoS**: HTTP, TCP, UDP Sensor Floods
   * **Reconnaissance**: Service Scanning, OS Fingerprinting
   * **Normal**: ทราฟฟิกปกติของอุปกรณ์สมาร์ทโฮมและเซ็นเซอร์
   * **Theft**: การดักจับข้อมูลรหัสผ่าน (Keylogging / Data Exfiltration)
2. **Configurable Downsampling**: สุ่มตัวอย่างทราฟฟิกตามจำนวนแถวที่กำหนด (ค่าตั้งต้น: 150,657 สำหรับ Train และ 20,000 สำหรับ Test) โดยแปลงฟิลด์ให้ตรงกับ Raw CSV Schema
3. **Data Cleansing**: ตรวจสอบ Sentinel Values, ตรวจสอบ Bounds ทางกายภาพ, ทำ Deduplication แฟล็ก และบันทึก `cleansing_audit.csv`
4. **Harmonization & 3-Table Separation**: แปลงเป็น 22 ฟิลด์มาตรฐานกลาง และแยกเป็น `features.csv` ($X$), `labels.csv` ($y$), `metadata.csv`

---

## 2. วิธีใช้งาน (Usage Guide)

### คำสั่งดาวน์โหลดข้อมูลจริงแบบอัตโนมัติ (Online Mode)
รันคำสั่งจากโฟลเดอร์นี้ (`data-pipeline/sub-dataset/BoT-IoT`):

```bash
# ดาวน์โหลดข้อมูลจริงตามขนาดมาตรฐาน (Train: 150,657 / Test: 20,000)
python download.py --source online --train_samples 150657 --test_samples 20000 --force

# ดาวน์โหลดขนาดเล็กสำหรับทดสอบ Pipeline ด่วน (Train: 10,000 / Test: 2,000)
python download.py --source online --train_samples 10000 --test_samples 2000 --force

# โหมดจำลองข้อมูลแบบออฟไลน์ (Offline Emulation Fallback)
python download.py --source emulate --train_samples 150657 --test_samples 20000
```

### การประมวลผลข้อมูล (Data Processing)
สามารถเลือกทำได้ 2 วิธี:

1. **รันผ่าน Master Runner อัตโนมัติ (แนะนำ)**:
   ```bash
   cd ../..
   python build_quad_dataset.py
   ```
   ระบบจะตรวจสอบไฟล์ใน `output/harmonized/` หากยังไม่มี จะเรียกประมวลผลเซลล์ใน Notebook ให้อัตโนมัติ

2. **รันผ่าน Jupyter Notebooks ด้วยตนเอง**:
   เปิดและรันเรียงตามลำดับ:
   * `cleansing.ipynb`
   * `harmonization.ipynb`
   * `eda.ipynb` (สำหรับตรวจสอบการกระจายตัวของข้อมูลหลังทำ Harmonization)

---

## 3. โครงสร้างโฟลเดอร์ (Directory Structure)

* `raw/`: เก็บไฟล์ดิบ `BoT_IoT_training-set.csv` และ `BoT_IoT_testing-set.csv`
* `download.py`: สคริปต์ดาวน์โหลดข้อมูลจริงจาก Online Mirror หรือสร้างข้อมูลจำลอง
* `cleansing.ipynb`: สมุดบันทึกตรวจสอบความสะอาดของข้อมูลและสร้าง Audit Report
* `eda.ipynb`: สมุดบันทึกสำรวจเชิงสถิติและการกระจายตัวของประเภทการโจมตี
* `harmonization.ipynb`: แปลงสกีมาเป็น 22 คอลัมน์มาตรฐานกลาง และสร้าง `features.csv`, `labels.csv`, `metadata.csv`
* `output/`:
  * `cleansing/`: ไฟล์ที่ผ่านการคลีนซิ่งแล้ว พร้อม `cleansing_audit.csv` และ `source_manifest.csv`
  * `harmonized/`: ตาราง `features.csv`, `labels.csv`, `metadata.csv` ที่พร้อมเชื่อมเข้าสู่ CENTRAL
