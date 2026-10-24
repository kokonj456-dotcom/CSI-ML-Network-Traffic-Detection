# Selected Core Features for 6-Class Multi-Domain Threat Classification

## Overview

This document details the **19 harmonized core features** utilized across Models 3, 4, 5, and 6 in the 6-Class Threat Classification Study. These features are extracted from the multi-domain harmonized pipeline spanning legacy network captures (NSL-KDD), contemporary enterprise attack testbeds (UNSW-NB15), campus intrusion datasets (CIC-IDS2017), and smart device environments (BoT-IoT).

---

## The 19 Selected Features

### 1. Continuous Flow Metrics (4 Features)

| Feature Name | Type | Mathematical Definition | Security Relevance |
| :--- | :--- | :--- | :--- |
| `log_duration` | Continuous | $\ln(1 + \max(0, \text{duration}))$ | Distinguishes ephemeral scans and rapid DoS bursts from persistent C2 beacons and interactive shell sessions. |
| `log_bytes_forward` | Continuous | $\ln(1 + \max(0, \text{bytes\_forward}))$ | Captures the volume of outbound payload, essential for identifying large payload injections, data exfiltration, or minimal probe packets. |
| `log_bytes_backward` | Continuous | $\ln(1 + \max(0, \text{bytes\_backward}))$ | Measures response volume from target servers, highlighting file downloads, web server responses, or silent drops. |
| `signed_log_bytes_ratio` | Continuous | $\ln(1 + \text{bytes\_forward}) - \ln(1 + \text{bytes\_backward})$ | Captures directional traffic asymmetry. Positive values indicate heavy sender-to-receiver transmission (DoS floods, brute-force); negative values indicate data-heavy responses (data exfiltration, large web payloads). |

---

### 2. Transport Protocol One-Hot Indicators (4 Features)

| Feature Name | Category | Base Protocol | Relevance to MITRE Tactics |
| :--- | :--- | :--- | :--- |
| `proto_tcp` | Binary Indicator | TCP | Primary transport for credential abuse (R2L SSH/FTP), web application exploits (TA0001), and standard C2 channels (TA0011). |
| `proto_udp` | Binary Indicator | UDP | Dominant protocol in high-volume reflection DoS/DDoS amplification attacks (TA0040) and DNS tunneling. |
| `proto_icmp` | Binary Indicator | ICMP | Common vector for network discovery (ping sweeps, TA0007) and smurf flood attacks. |
| `proto_other` | Binary Indicator | Other Protocols | Flags non-standard or encapsulated traffic (GRE, ESP, SCTP) often used in stealth lateral movement. |

---

### 3. Application Service Group Indicators (7 Features)

| Feature Name | Category | Port Mapping | Target Attack Classes |
| :--- | :--- | :--- | :--- |
| `service_dns` | Binary Indicator | Port 53 (UDP/TCP) | Reconnaissance sweeps, DNS amplification DoS, and covert DNS tunneling. |
| `service_ftp` | Binary Indicator | Ports 20, 21 (TCP) | Credential brute forcing (`ftp_write`, `FTP-Patator`) and unauthorized remote file retrieval (R2L). |
| `service_http` | Binary Indicator | Port 80 (TCP) | Web exploitation (SQLi, XSS), Slowloris DoS, and unencrypted C2 communication. |
| `service_https_ssl` | Binary Indicator | Port 443 (TCP) | Modern encrypted C2 beaconing, secure web exploits, and TLS-based application DoS. |
| `service_smtp` | Binary Indicator | Port 25 (TCP) | Mailbomb DoS attacks and phishing initial access vectors. |
| `service_ssh` | Binary Indicator | Port 22 (TCP) | Remote credential guessing (`guess_passwd`, `SSH-Patator`), interactive remote access (R2L). |
| `service_other` | Binary Indicator | Ephemeral / Custom Ports | Database ports (SQL, Oracle), IoT telemetry, and non-standard backdoor ports. |

---

### 4. Connection State Group Indicators (4 Features)

| Feature Name | Category | State Representation | Security Significance |
| :--- | :--- | :--- | :--- |
| `state_established` | Binary Indicator | Full 3-way handshake (`SF`, `FIN`, `CON`) | Normal traffic, successful exploitation, credential authentication, and interactive command sessions. |
| `state_no-reply` | Binary Indicator | Unanswered SYN / unidirectional flows (`S0`, `REQ`, `INT`) | Hallmarks of SYN flood DoS attacks and blind port scanning reconnaissance. |
| `state_reset` | Binary Indicator | Connection reset (`RST`, `REJ`, `RSTO`, `RSTR`) | Closed port probe scanning and actively terminated sessions. |
| `state_other` | Binary Indicator | Half-open or fragmented states (`URG`, `PAR`) | Evasion techniques, malformed TCP packets, and fuzzing payloads. |

---

## Feature Comparison: Native vs Selected Core

| Property | NSL-KDD Native | UNSW-NB15 Native | 19 Selected Core Features |
| :--- | :---: | :---: | :---: |
| Feature Count | 41 features (121 encoded) | 42 features (194 encoded) | **19 features** |
| Cross-Dataset Compatibility | No (NSL only) | No (UNSW only) | **Universal (NSL, UNSW, CIC, BoT)** |
| Computational Overhead | Moderate | High (194 sparse columns) | **Minimal (Fast inference and compact tree models)** |
| Dependency on Testbed Artifacts | High (Window metrics) | High (Jitter, packet TTL) | **Zero (Universal flow-level attributes)** |

