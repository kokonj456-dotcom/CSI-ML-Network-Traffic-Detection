# BoT-IoT Dataset Guide

## 1. Overview
The **BoT-IoT** dataset was created by the Cyber Range Lab of UNSW Canberra in 2018. It presents a realistic simulated IoT environment (smart home, MQTT, weather sensors) combined with massive IoT botnet attacks such as Mirai.

## 2. Attack Categories & MITRE ATT&CK Mapping

| Raw Category | Subcategory | Pipeline Category | Target 6-Class ID | MITRE ATT&CK Tactic | Technique |
|---|---|---|---|---|---|
| Normal | Normal | Normal | 0 | Baseline Operations | - |
| DoS / DDoS | UDP / TCP / HTTP | DoS | 1 | Impact (`TA0040`) | T1498 (Network DoS) |
| Reconnaissance | Service_Scan / OS_Fingerprint | Probe | 2 | Discovery / Recon (`TA0007`/`TA0043`) | T1595, T1046 |
| Exploits | Keylogging | Exploits | 3 | Initial Access (`TA0001`) | T1190 |
| R2L | BruteForce (Telnet/SSH) | R2L | 4 | Credential Access (`TA0006`) | T1110 (Brute Force) |
| Generic | Data_Theft | Generic | 5 | Command and Control (`TA0011`) | T1071 |

## 3. Core Flow Schema Mapping to Joint Contract
- `duration`: `dur` (seconds)
- `protocol`: `proto` (tcp, udp, icmp, other)
- `bytes_forward`: `sbytes`
- `bytes_backward`: `dbytes`
- `service_group`: mapped by port (80/8080 -> http, 443 -> https_ssl, 53 -> dns, 21 -> ftp, 22/23 -> ssh, other -> other)
- `conn_state_group`: `state` (CON/FIN -> established, REQ/INT -> no-reply, RST -> reset, other -> other)

