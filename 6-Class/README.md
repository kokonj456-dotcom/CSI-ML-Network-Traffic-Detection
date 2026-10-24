# 6-Class Threat Taxonomy & Quad-Domain Harmonization Study

## 1. Project Overview & Academic Directive

In accordance with academic guidance, this study evaluates multi-domain network intrusion detection without removing or discarding any attack category. Real-world network captures contain severe class imbalances where critical threats (such as **User-to-Root (U2R)** privilege escalation and **Remote-to-Local (R2L)** credential abuse) appear with extreme rarity compared to benign background traffic and volumetric Denial of Service (DoS) attacks.

This study implements a **6-Class Threat Taxonomy** grounded in the **MITRE ATT&CK Enterprise Matrix**, preserving **100.00% of all attack instances** across four landmark intrusion detection datasets:
1. **NSL-KDD** (Legacy Baseline - 1999)
2. **UNSW-NB15** (Contemporary Enterprise - 2015)
3. **CIC-IDS2017** (Modern University Campus - 2017)
4. **BoT-IoT** (Smart Environment & IoT - 2018)

---

## 2. 6-Class MITRE ATT&CK Threat Taxonomy

| Class ID | Target Threat Category | MITRE ATT&CK Tactic | MITRE ID | Included Dataset Categories | Dataset Sources |
| :-: | :--- | :--- | :-: | :--- | :--- |
| **0** | **Benign / Normal** | Baseline Operations | - | Normal, BENIGN, Normal IoT | NSL-KDD, UNSW-NB15, CIC-IDS2017, BoT-IoT |
| **1** | **Denial of Service (DoS/DDoS)** | Impact | `TA0040` | DoS, DDoS, smurf, neptune, Hulk, GoldenEye, Slowloris, Mirai UDP Flood | All 4 Datasets |
| **2** | **Reconnaissance & Probing** | Reconnaissance / Discovery | `TA0043` / `TA0007` | Probe, portsweep, satan, nmap, PortScan, Service/OS Fingerprint | All 4 Datasets |
| **3** | **Exploits & PrivEsc** | Initial Access / Privilege Escalation | `TA0001` / `TA0004` | Exploits, Shellcode, U2R (buffer_overflow, rootkit), Web Attacks (SQLi, XSS) | UNSW-NB15, NSL-KDD, CIC-IDS2017 |
| **4** | **Credential Abuse (R2L)** | Credential Access / Initial Access | `TA0006` / `TA0001` | R2L (guess_passwd, warezclient), SSH-Patator, FTP-Patator, Default Auth Brute-force | NSL-KDD, CIC-IDS2017, BoT-IoT |
| **5** | **Malware, C2 & Botnet** | Command & Control / Lateral Movement | `TA0011` / `TA0008` | Generic, Fuzzers, Backdoors, Worms, ARES Botnet, IoT Data Theft | UNSW-NB15, CIC-IDS2017, BoT-IoT |

---

## 3. Experimental Model Matrix (7 Models Evaluated)

| Model | Architecture | Training Scale | Features | Test Accuracy | Macro F1 | R2L Recall | Benign FPR | Status / Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Model 1** | NSL Native Full Features | 125,973 | 41 Native (121 enc) | 77.60% *(In-domain)* | 46.19% | 8.60% | 2.88% | **Siloed Baseline**: Blind to modern malware (0.00%) |
| **Model 2** | UNSW Native Full Features | 175,341 | 42 Native (194 enc) | 77.94% *(In-domain)* | 53.55% | 0.00% | 24.14% | **Siloed Baseline**: Blind to credential abuse R2L (0.00%) |
| **Model 3** | Harmonized Standard (Unweighted) | 301,314 | 19 Core Features | 76.13% | 62.38% | 8.15% | 18.51% | **Standard Baseline**: Suffers severe majority bias |
| **Model 4** | Harmonized + Borderline-SMOTE | 325,319 | 19 Core Features | 76.22% | 66.80% | 29.46% | 19.55% | **Best 2-Domain Model**: SMOTE boosts R2L detection |
| **Model 5** | Harmonized + Class-Weighted | 301,314 | 19 Core Features | 68.98% | 59.49% | 29.88% | 34.84% | **Unstable**: Spikes False Positive Rate to 34.84% |
| **Model 6** | Harmonized Hybrid (SMOTE + Weights) | 325,319 | 19 Core Features | 68.95% | 59.40% | 29.60% | 34.83% | **Redundant**: Combining 50x weights degrades precision |
| **Model 7** | **Quad Foundation + Borderline-SMOTE** | **629,582** | **19 Core Features** | **81.13%** | **77.03%** | **52.64%** | **14.44%** | **Quad Champion**: Highest Acc, Macro F1, and R2L Recall |

---

## 4. Key Breakthroughs in Model 7 (Quad Foundation + SMOTE)

1. **Equalized 1:1 Scaling Across 4 Domains**:
   - Training combines 50% Legacy/Enterprise (`UNSW + NSL = 301,314 flows`) and 50% Modern Campus & Smart IoT (`CIC + BoT = 301,314 flows`).
   - Total raw training set: **602,628 flows**.
2. **Natural Diversity for Minority Attacks**:
   - In NSL+UNSW alone, Class 4 (R2L) had only 995 training flows.
   - Adding CIC-IDS2017 (`SSH-Patator` & `FTP-Patator`) and BoT-IoT (`Telnet/SSH default credential scans`) supplied **12,051 additional real attack flows**, bringing Class 4 to 13,046 flows.
3. **Targeted Borderline-SMOTE Synthesis**:
   - Applying Borderline-SMOTE boosted Class 4 to **40,000 flows**, expanding total training to **629,582 flows**.
4. **Empirical Results Across 144,876 Benchmark Flows**:
   - **Quad Global Accuracy**: **81.13%** (+4.91% higher than Model 4).
   - **Quad Global Macro F1**: **77.03%** (+10.23% higher than Model 4).
   - **R2L / Credential Abuse Recall**: **52.64%** (more than 1 in 2 caught, vs 8.15% in standard Model 3).
   - **Benign False Alarm Rate (FPR)**: Dropped to **14.44%** (lowest among all multi-domain models).
   - **In-Domain Campus & IoT Performance**: **92.45%** on CIC-IDS2017 and **99.16%** on BoT-IoT telemetry.

---

## 5. How to Run the Web Dashboard

Run the included runner script:
```bash
bash 6-Class/run.sh
```
Or view the live server currently running at:
[http://localhost:3000](http://localhost:3000)
