# CIC-IDS2017 Dataset Guide

## 1. Overview
The **CIC-IDS2017** dataset was collected by the Canadian Institute for Cybersecurity (University of New Brunswick) in 2017. It covers realistic background network traffic alongside modern attack scenarios captured across five days.

## 2. Attack Categories & MITRE ATT&CK Mapping

| Raw Attack Name | Pipeline Category | Target 6-Class ID | MITRE ATT&CK Tactic | Technique |
|---|---|---|---|---|
| BENIGN | Normal | 0 | Baseline Operations | - |
| DoS Hulk / GoldenEye / Slowloris | DoS | 1 | Impact (`TA0040`) | T1498, T1499 |
| PortScan | Probe | 2 | Discovery / Recon (`TA0007`/`TA0043`) | T1595, T1046 |
| Web Attack (SQLi / XSS) | Exploits | 3 | Initial Access (`TA0001`) | T1190 |
| SSH-Patator / FTP-Patator | R2L | 4 | Credential Access (`TA0006`) | T1110 (Brute Force) |
| Bot (ARES Botnet) | Generic | 5 | Command and Control (`TA0011`) | T1071 |

## 3. Core Flow Schema Mapping to Joint Contract
- `duration`: `flow_duration` (converted to seconds)
- `protocol`: `protocol` (tcp, udp, icmp, other)
- `bytes_forward`: `total_fwd_bytes`
- `bytes_backward`: `total_bwd_bytes`
- `service_group`: mapped from destination ports (80/8080 -> http, 443 -> https_ssl, 53 -> dns, 21 -> ftp, 22 -> ssh, 25 -> smtp, other -> other)
- `conn_state_group`: `flow_state` (established, no-reply, reset, other)

