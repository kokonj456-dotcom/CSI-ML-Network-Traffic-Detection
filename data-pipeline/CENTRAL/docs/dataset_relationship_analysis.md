# ความสัมพันธ์และความต่างของข้อมูลกลาง NSL-KDD / UNSW-NB15

วิเคราะห์จาก `output/splits/train_full` ก่อนสุ่มจำนวนต่อแหล่งให้เท่ากัน ใช้ NSL-KDD 100,778 แถว และ UNSW-NB15 140,273 แถว ไม่ใช้ validation/test การแยก Normal/Attack ใช้ label เพื่อบรรยายข้อมูลเท่านั้น ไม่มีการฝึกโมเดล

แถวสองชุดไม่ใช่เหตุการณ์ที่จับคู่กัน จึงไม่หาค่า correlation ข้ามแหล่งด้วยการเรียงแถว แต่คำนวณความสัมพันธ์ภายในแต่ละแหล่งแล้วเปรียบเทียบกัน

## ผลสำคัญ

| คู่คอลัมน์ | Spearman NSL | Spearman UNSW |
|---|---:|---:|
| duration / bytes_forward | 0.2267 | 0.7521 |
| duration / bytes_backward | 0.1496 | 0.7563 |
| bytes_forward / bytes_backward | 0.7004 | 0.7910 |

Spearman อยู่ระหว่าง -1 ถึง 1 ใช้อธิบายความสัมพันธ์เชิงอันดับ ไม่ใช่เหตุและผล ความสัมพันธ์ของระยะเวลากับ bytes ต่างกันมากระหว่างแหล่ง

เมื่อแยกเฉพาะ Normal ความสัมพันธ์ bytes_forward / bytes_backward เป็น 0.3101 ใน NSL และ 0.7951 ใน UNSW แสดงว่าความสัมพันธ์รวมอาจได้รับอิทธิพลจากการผสมกลุ่ม traffic จึงไม่ควรเลือก feature จาก correlation รวมเพียงอย่างเดียว

| Feature | สัดส่วนศูนย์ NSL | สัดส่วนศูนย์ UNSW | KS statistic |
|---|---:|---:|---:|
| duration | 92.02% | 1.49% | 0.9053 |
| bytes_forward | 39.24% | 0.00% | 0.5274 |
| bytes_backward | 53.97% | 48.04% | 0.1492 |

KS เป็นระยะห่างสูงสุดระหว่างการแจกแจงสะสม อยู่ในช่วง 0–1 ค่าสูงแสดงความต่างมาก ไม่ได้พิสูจน์ว่านิยามคอลัมน์ผิด duration ควรตรวจความละเอียดเวลาและนิยามการวัดเป็นอันดับแรก ส่วน bytes ควรตรวจวิธีนับ header/payload และทิศทาง

สำหรับหมวดหมู่ใช้ Jensen–Shannon distance ฐาน 2 (0–1) แทน correlation ของรหัสหมวดหมู่ ผลรวม: protocol 0.4549, service_group 0.3156, conn_state_group 0.2901 ส่วน Normal-only service_group มีระยะห่าง 0.5922 จึงควรตรวจองค์ประกอบบริการและ mapping เพิ่ม

ความสัมพันธ์ระหว่างหมวดใช้ Cramer's V แบบไม่แก้ bias: protocol / conn_state_group เป็น 0.2779 ใน NSL และ 0.7645 ใน UNSW; เฉพาะ Normal เป็น 0.0893 และ 0.6928 ควรตรวจ state mapping และ protocol mix ก่อนใช้ state เป็นแกนจัด cluster

## การตัดสินใจที่แนะนำ

1. เก็บทุกคอลัมน์ไว้ก่อน ตรวจ duration และ bytes จากนิยามต้นทาง ไม่ปรับค่าเพื่อบังคับให้ distribution เหมือนกัน
2. ตรวจ service/state mapping พร้อมสัดส่วน other และ unknown แยก source และ label
3. เปรียบเทียบ distribution ภายใน protocol/service เดียวกันเพิ่มเติม เพื่อลดอิทธิพลจากสัดส่วน traffic ที่ต่างกัน
4. เก็บ baseline ที่มีและไม่มี duration/state สำหรับทดลองภายหลัง ตรวจผลแยก dataset และตรวจว่า cluster สะท้อน source มากกว่าพฤติกรรมหรือไม่
5. ไม่ลบ bytes_backward จาก correlation รวมที่สูง เพราะความสัมพันธ์เปลี่ยนมากเมื่อแยก Normal/Attack

## ทำซ้ำและอ่านผลเต็ม

รันจากรากโครงการ: `เปิด data-pipeline/CENTRAL/analyze_dataset_relationships.ipynb แล้วรันทุก cell ตามลำดับ`

ผล CSV อยู่ที่ `data-pipeline/CENTRAL/output/reports/dataset_relationships/`: sample_counts, numeric_correlations (Pearson/Spearman ทั้งค่าดิบและ log1p), correlation_comparison, numeric_distribution_shift, categorical_distribution_shift, categorical_associations และ analysis_manifest.json

ข้อจำกัด: วัดบน output harmonization ปัจจุบัน ยังไม่ยืนยันความเทียบเท่าด้านความหมาย ไม่ใช่ผลประเมินโมเดล และการแยก Normal/Attack ยังไม่ควบคุมความต่างของ protocol/service หรือชนิดการโจมตีทั้งหมด


หมายเหตุ: ตารางตัวเลขในเอกสารนี้เป็น snapshot จากการวิเคราะห์ครั้งก่อน; ให้รัน notebook เพื่อสร้าง CSV จาก train_full ปัจจุบันก่อนใช้อ้างอิงผลล่าสุด.
