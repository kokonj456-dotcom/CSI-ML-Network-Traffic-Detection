# Selected Features Specification (`joint_v1` Profile)

This document specifies the exact set of **19 harmonized model input features** derived from 6 fundamental network flow attributes across **UNSW-NB15** and **NSL-KDD**.

---

## 1. Overview & Architecture

The harmonized feature profile (`joint_v1`) focuses exclusively on **Flow-Level Telemetry** (NetFlow / IPFIX compatible metadata). It intentionally avoids reliance on deep packet inspection (DPI) or testbed-specific hardware metrics (such as TCP window size, jitter, and inter-arrival timers), ensuring universal portability across different networking hardware and eras.

```
Raw Network Flow Attributes (6 Core)
  ├── 1. Duration (duration / dur)
  ├── 2. Forward Bytes (src_bytes / sbytes)
  ├── 3. Backward Bytes (dst_bytes / dbytes)
  ├── 4. Protocol (protocol_type / proto)
  ├── 5. Application Service (service)
  └── 6. Connection State (flag / state)
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

| # | Feature Name | Source Mappings (NSL / UNSW) | Network Diagnostic Meaning |
| :-: | :--- | :--- | :--- |
| **16** | `conn_state_established` | NSL: `SF` <br/>UNSW: `FIN`, `CON` | Normal completed 3-way handshake and orderly session closure. |
| **17** | `conn_state_no_reply` | NSL: `S0`, `S1`, `S2`, `S3` <br/>UNSW: `INT`, `REQ`, `RSP` | Connection initiated but unanswered or timed out (SYN floods, unresponsive hosts). |
| **18** | `conn_state_reset` | NSL: `REJ`, `RSTOS0`, `RSTR` <br/>UNSW: `CLO`, `RST` | Connection actively rejected or reset (port sweeps against closed ports). |
| **19** | `conn_state_other` | NSL: `OTH`, `SH` <br/>UNSW: `ACC`, `PAR`, `URN`, `-` | Malformed flags, partial handshakes, or non-standard TCP terminations. |

---

## 6. Source Column Mapping Reference

| Core Feature Concept | NSL-KDD Source Column | UNSW-NB15 Source Column | Data Type | Transformation Applied |
| :--- | :--- | :--- | :--- | :--- |
| **Duration** | `duration` | `dur` | Float (seconds) | `log1p(x)` |
| **Forward Bytes** | `src_bytes` | `sbytes` | Integer (bytes) | `log1p(x)` |
| **Backward Bytes** | `dst_bytes` | `dbytes` | Integer (bytes) | `log1p(x)` |
| **Directional Ratio** | Computed | Computed | Float | `log1p(fwd) - log1p(bwd)` |
| **Protocol** | `protocol_type` | `proto` | String | One-Hot Encoding (4 bins) |
| **Service Group** | `service` | `service` | String | Group Mapping &rarr; One-Hot (7 bins) |
| **Connection State** | `flag` | `state` | String | State Mapping &rarr; One-Hot (4 bins) |

---

## 7. Predictive Impact & Empirical Justification

From the XGBoost feature importance evaluations on 120,000 harmonized training samples:
- **Top 5 Features by Gain**:
  1. `service_dns` (Gain: 1,021.65)
  2. `log_bytes_backward` (Gain: 185.20)
  3. `service_other` (Gain: 172.48)
  4. `signed_log_bytes_ratio` (Gain: 141.44)
  5. `conn_state_no_reply` (Gain: 122.29)
- **Empirical Accuracy Retention**:
  - Model 1 (All 42 UNSW Features): **95.10%** test accuracy.
  - Model 2 (Selected 19 Core Features): **95.93%** test accuracy (+0.83% gain).
  - Model 3 (Harmonized UNSW+NSL Core Features): **95.57%** test accuracy on UNSW and **82.22%** test accuracy on NSL-KDD (+28.56% cross-dataset generalizability).

