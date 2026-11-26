# CENTRAL-5M Big Data Pipeline

## Overview
`CENTRAL-5M` is the production-scale multi-domain network flow dataset comprising **5,036,579 training records** harmonized across 6 distinct network environments, paired with canonical validation (121,199 records) and test (143,095 records) splits for cross-model comparability with Models M1-M8 and M9.

It powers Model M9 (Unified Production Engine) and was built under strict compliance with the project's zero-leakage, cross-domain feature contract.

---

## 1. Directory Structure

```
data-pipeline/CENTRAL-5M/
├── README.md                           # Comprehensive documentation
├── feature_contract.json               # Schema specification across all 6 datasets
├── dataset_registry.json               # Source dataset provenance and roles
├── build_dataset_5m.ipynb              # Interactive inspection and execution notebook
└── output/
    ├── harmonized/                     # Complete multi-domain harmonized dataset
    │   ├── features.parquet            # 5,036,579 rows x 20 cols (record_id + 19 features)
    │   ├── labels.parquet              # 5,036,579 rows x 5 cols
    │   └── metadata.parquet            # 5,036,579 rows x 2 cols
    ├── splits/                         # Deterministic training and benchmark splits
    │   ├── train/                      # 5,036,579 records in Parquet format
    │   ├── validation/                 # 121,199 records (canonical benchmark)
    │   └── test/                       # 143,095 records (canonical benchmark)
    ├── feature_engineering/
    │   ├── preprocessor.joblib         # Fitted StandardScaler + OneHotEncoder (joint_v2)
    │   └── feature_schema.json         # Feature specification and data types
    └── reports/
        ├── audit.json                  # Record counts, hash digests, invariants
        ├── label_mapping.csv           # Source to MITRE category cross-tabulation
        └── source_splits.csv           # Breakdown of records per domain across splits
```

---

## 2. Source Datasets & Domain Breakdown

| Dataset | Split | Row Count | Attack Ratio | Domain Profile |
| :--- | :--- | :--- | :--- | :--- |
| **CIC-IDS2017** | Train | 2,000,000 | 48.2% | Modern Enterprise Canadian LAN (DoS, DDoS, PortScan, BruteForce) |
| **BoT-IoT** | Train | 1,800,000 | 66.7% | Smart Home & Sensor IoT Botnets (High-volume DDoS, Recon) |
| **CIC-IDS2018** | Train | 619,346 | 60.1% | AWS Cloud Infrastructure (SSH/FTP BruteForce) |
| **UNSW-NB15** | Train | 257,673 | 63.9% | Perimeter Security & Contemporary Network Attacks |
| **ToN-IoT** | Train | 211,043 | 68.3% | Next-gen Industry 4.0 & Industrial IoT (Injection, Backdoors) |
| **NSL-KDD** | Train | 148,517 | 48.1% | Canonical Historic Benchmark |
| **Train Total** | **Train** | **5,036,579** | **54.3%** | **Comprehensive Multi-Domain Training Corpus** |
| **Validation** | Validation | 121,199 | 62.6% | Canonical Project Benchmark Validation Split |
| **Test** | Test | 143,095 | 57.3% | Canonical Project Benchmark Test Split |
| **Grand Total**| **All Splits** | **5,300,873** | **54.6%** | **Combined Pipeline Universe** |

---

## 3. Storage Format & Efficiency

`CENTRAL-5M` utilizes **Parquet-First** columnar format (`.parquet` via PyArrow / Snappy compression) to maximize I/O throughput and eliminate Git storage bottlenecks:
- `features.parquet` (5.04M rows): **69.9 MB** (vs. ~950 MB uncompressed CSV)
- `labels.parquet` (5.04M rows): **26.0 MB** (vs. ~380 MB uncompressed CSV)
- `metadata.parquet` (5.04M rows): **24.2 MB** (vs. ~420 MB uncompressed CSV)
- Full training corpus occupies only **~120 MB**, enabling sub-second batch loads.

---

## 4. Feature Specification (19 Canonical Features)

All flows are normalized using the `joint_v2` pipeline preprocessor into 19 numerical columns:

1. **Continuous Physical Flow (4)**:
   - `log_duration`: $\ln(1 + \text{duration})$
   - `log_bytes_forward`: $\ln(1 + \text{bytes\_forward})$
   - `log_bytes_backward`: $\ln(1 + \text{bytes\_backward})$
   - `signed_log_bytes_ratio`: $\ln(1 + \text{bytes\_forward}) - \ln(1 + \text{bytes\_backward})$
2. **Protocol One-Hot Encoding (4)**:
   - `proto_tcp`, `proto_udp`, `proto_icmp`, `proto_other`
3. **Service Group One-Hot Encoding (7)**:
   - `service_dns`, `service_ftp`, `service_http`, `service_https_ssl`, `service_smtp`, `service_ssh`, `service_other`
4. **Connection State One-Hot Encoding (4)**:
   - `state_established`, `state_no-reply`, `state_reset`, `state_other`

---

## 5. Label Space & MITRE ATT&CK Taxonomy

Flows are mapped to a 6-class MITRE ATT&CK taxonomy:
- `0` - **Benign / Normal**: Baseline Operations (2,300,531 flows)
- `1` - **Denial of Service (DoS)**: TA0040: Impact (2,122,048 flows)
- `2` - **Reconnaissance & Probing**: TA0043/TA0007: Discovery (268,792 flows)
- `3` - **Exploits & PrivEsc**: TA0001/TA0004: Initial Access & PrivEsc (106,872 flows)
- `4` - **Credential Abuse (R2L)**: TA0006: Credential Access (130,093 flows)
- `5` - **Malware, C2 & Botnet**: TA0011/TA0008: C2 & Lateral Movement (108,243 flows)

---

## 6. How to Rebuild & Verify

### Via Standalone CLI
To verify data integrity without rebuilding:
```bash
python data-pipeline/build_central_5m.py --verify-only
```

To rebuild all Parquet files and reports from source:
```bash
python data-pipeline/build_central_5m.py
```

### Via Jupyter Notebook
Open and run all cells in [build_dataset_5m.ipynb](file:///Users/bb/Documents/GitHub/CSI_ML_Final/data-pipeline/CENTRAL-5M/build_dataset_5m.ipynb).

---

## 7. Audit Invariants

The automated test suite verifies:
- `train_row_count_ge_5m`: Exactly 5,036,579 rows in `train`.
- `validation_row_count_canonical`: Exactly 121,199 rows matching canonical CENTRAL.
- `test_row_count_canonical`: Exactly 143,095 rows matching canonical CENTRAL.
- `feature_count_exact_19`: Exactly 19 numerical model features.
- `all_features_finite`: No NaN or Inf values in feature tensors.
- `no_duplicate_train_record_ids`: Unique IDs across all training flows.
