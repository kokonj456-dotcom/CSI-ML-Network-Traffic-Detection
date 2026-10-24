# Selected Features Specification (`joint_v1` Profile)

This document specifies the exact set of **19 harmonized model input features** derived from 6 fundamental network flow attributes across **UNSW-NB15**, **NSL-KDD**, **CIC-IDS2017**, and **BoT-IoT**.

---

## 1. Overview & Architecture

The harmonized feature profile (`joint_v1`) focuses exclusively on **Flow-Level Telemetry** (NetFlow / IPFIX compatible metadata). It intentionally avoids reliance on deep packet inspection (DPI) or testbed-specific hardware metrics (such as TCP window size, jitter, and inter-arrival timers), ensuring universal portability across different networking hardware and eras.

```
Raw Network Flow Attributes (6 Core)
  ├── 1. Duration (duration / dur / Flow Duration)
  ├── 2. Forward Bytes (src_bytes / sbytes / Total Length of Fwd Packet)
  ├── 3. Backward Bytes (dst_bytes / dbytes / Total Length of Bwd Packet)
  ├── 4. Protocol (protocol_type / proto / Protocol)
  ├── 5. Application Service (service / Dst Port / dport)
  └── 6. Connection State (flag / state / Flags)
          │
          ▼ Feature Engineering (Log1p, Directional Ratio, One-Hot Encoding)
Model Input Vector: 19 Features
```

---

## 2. Numerical Engineered Features (4 Features)

All byte and duration metrics are log-transformed using `log1p(x) = ln(1 + x)` to compress heavy-tailed power-law distributions typical of network traffic.

| # | Feature Name | Mathematical Definition | Network Behavioral Rationale |
| :-: | :--- | :--- | :--- |
| **1** | `log_duration` | $\ln(1 + \max(\text{duration}, 0))$ | Separates micro-duration automated probes/scans ($<0.001\text{s}$) from interactive human sessions. |
| **2** | `log_bytes_forward` | $\ln(1 + \max(\text{bytes\_forward}, 0))$ | Quantifies volume sent from source to destination (detects volumetric DoS floods and large upload activity). |
| **3** | `log_bytes_backward` | $\ln(1 + \max(\text{bytes\_backward}, 0))$ | Quantifies server response volume. Near-zero values indicate unreplied floods, crashes, or timeouts. |
| **4** | `signed_log_bytes_ratio` | $\text{log\_bytes\_forward} - \text{log\_bytes\_backward}$ | **Measures directional asymmetry**. Benign sessions show balanced request-response exchanges; bot attacks exhibit extreme one-way push asymmetry. |

---

## 3. Protocol Categorical Features (4 Features, One-Hot Encoded)

Encodes standard Layer 4 transport protocols. Unknown or unlisted protocols map to `protocol_other`.

| # | Feature Name | Value Range | Behavioral Discrimination |
| :-: | :--- | :---: | :--- |
| **5** | `protocol_tcp` | 0 or 1 | Connection-oriented traffic with handshake (Web, SSH, FTP, SYN Flood DoS). |
| **6** | `protocol_udp` | 0 or 1 | Connectionless traffic (DNS reflection, automated UDP flood attacks, generic bot scripts). |
| **7** | `protocol_icmp` | 0 or 1 | Network diagnostic and error messages (Ping sweeps, Smurf amplification attacks). |
| **8** | `protocol_other` | 0 or 1 | Non-standard or raw IP protocols (OSPF, IGMP, GRE tunnels). |

---

## 4. Service Group Categorical Features (7 Features, One-Hot Encoded)

Aggregates over 70 fine-grained application layer ports and service names into 7 universal core functional groups. Unrecognized services map to `service_other`.

| # | Feature Name | Aggregated Services & Ports | Threat Profile & Behavioral Relevance |
| :-: | :--- | :--- | :--- |
| **9** | `service_dns` | DNS (Port 53) | Detects DNS amplification, query flooding, and tunnel exfiltration. |
| **10** | `service_ftp` | FTP, FTP-Data (Ports 20, 21) | Detects unencrypted file transfer anomalies and brute-force logins. |
| **11** | `service_http` | HTTP (Port 80) | Plaintext web application traffic and HTTP GET/POST flood vectors. |
| **12** | `service_https_ssl` | HTTPS, SSL, TLS (Port 443) | Encrypted modern web traffic baseline. |
| **13** | `service_smtp` | SMTP, POP3, IMAP (Ports 25, 110, 143) | Mail delivery anomalies, spam bots, and mail relay abuse. |
| **14** | `service_ssh` | SSH, Telnet (Ports 22, 23) | Remote administrative access, brute-force password guessing. |
| **15** | `service_other` | All other ports and unassigned services | Obscure or ephemeral high ports frequently utilized by command-and-control (C2) or port scans. |

---

## 5. Connection State Categorical Features (4 Features, One-Hot Encoded)

Maps vendor-specific and dataset-specific TCP flags and flow states into 4 canonical connection life-cycle states.

| # | Feature Name | Source Mappings (NSL / UNSW / CIC / BoT) | Network Diagnostic Meaning |
| :-: | :--- | :--- | :--- |
| **16** | `conn_state_established` | NSL: `SF` <br/>UNSW/BoT: `FIN`, `CON` <br/>CIC: `ACK`, `SYN-ACK` | Normal completed 3-way handshake and orderly session closure. |
| **17** | `conn_state_no_reply` | NSL: `S0`, `S1`, `S2`, `S3` <br/>UNSW/BoT: `INT`, `REQ`, `RSP` <br/>CIC: Unanswered `SYN` | Connection initiated but unanswered or timed out (SYN floods, unresponsive hosts). |
| **18** | `conn_state_reset` | NSL: `REJ`, `RSTOS0`, `RSTR` <br/>UNSW/BoT: `CLO`, `RST` <br/>CIC: `RST` Flag | Connection actively rejected or reset (port sweeps against closed ports). |
| **19** | `conn_state_other` | NSL: `OTH`, `SH` <br/>UNSW/BoT: `ACC`, `PAR`, `URN`, `-` | Malformed flags, partial handshakes, or non-standard TCP terminations. |

---

## 6. Multi-Dataset Source Column Mapping Reference

| Core Feature Concept | NSL-KDD (1999) | UNSW-NB15 (2015) | CIC-IDS2017 (2017) | BoT-IoT (2018) | Transform Applied |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Duration** | `duration` | `dur` | `Flow Duration` ($\mu\text{s} / 10^6$) | `dur` | `log1p(x)` |
| **Forward Bytes** | `src_bytes` | `sbytes` | `Total Length of Fwd Packet` | `sbytes` | `log1p(x)` |
| **Backward Bytes** | `dst_bytes` | `dbytes` | `Total Length of Bwd Packet` | `dbytes` | `log1p(x)` |
| **Directional Ratio** | Computed | Computed | Computed | Computed | `log1p(fwd) - log1p(bwd)` |
| **Protocol** | `protocol_type` | `proto` | `Protocol` (6, 17, 1) | `proto` | One-Hot (4 bins) |
| **Service Group** | `service` | `service` | Mapped from `Dst Port` | Mapped from `dport` | Group Mapping &rarr; One-Hot (7 bins) |
| **Connection State** | `flag` | `state` | Mapped from Flag bits | `state` | State Mapping &rarr; One-Hot (4 bins) |

---

## 7. Predictive Impact & Empirical Justification (7-Model Benchmark)

- **Model 1 (42 Raw Features, UNSW only)**: **95.10%** on UNSW. **0% compatibility** on NSL, CIC-IDS2017, and BoT-IoT (Incompatible schema).
- **Model 2 (19 Core Features, UNSW only)**: **95.93%** on UNSW. Drops to **53.66%** on NSL-KDD, **41.20%** on CIC-IDS2017, and **48.50%** on BoT-IoT.
- **Model 3 (19 Core Features, 1:1 UNSW+NSL 120k)**: **95.57%** on UNSW, **82.22%** on NSL-KDD, **65.40%** on CIC-IDS2017, **72.10%** on BoT-IoT.
- **Model 4 (19 Core Features, All UNSW+NSL 245k)**: **95.86%** on UNSW, **82.40%** on NSL-KDD, **74.20%** on CIC-IDS2017, **81.30%** on BoT-IoT.
- **Model 5 (19 Core Features, Quad-Domain Balanced 150k)**: **94.98%** on UNSW, **83.25%** on NSL-KDD, **99.12%** on CIC-IDS2017, **99.88%** on BoT-IoT, and **93.01%** on the **Quad Global Benchmark (93,769 total test flows)**.
- **Model 6 (19 Core Features, Full-Scale Quad ALL DATA 285k)**: **95.22%** on UNSW, **83.19%** on NSL-KDD, **99.00%** on CIC-IDS2017, **99.84%** on BoT-IoT, and **93.15%** on the **Quad Global Benchmark (93,769 total test flows)**.
- **Model 7 (19 Core Features, Mega-Scale Quad 1.04M)**: **94.67%** on UNSW, **85.66%** on NSL-KDD, **99.76%** on CIC-IDS2017, **99.96%** on BoT-IoT, **93.34%** on Standard Quad Global (93k), and **97.85%** on **Mega Global Test (303,769 total test flows)**. Pushing data volume beyond 1 Million flows solidifies enterprise-grade generalization across all modern and legacy topologies.
