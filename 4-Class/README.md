# 4-Class Threat Taxonomy & Quad-Dataset Harmonization Study

This folder contains the complete code, trained experiment results, benchmark test data, and standalone presentation web dashboard for the **4-Class Network Threat Taxonomy & Multi-Domain Harmonization Study**.

---

## 1. Research Hypotheses & Key Findings

1. **Feature Pruning & Predictive Retention**:
   - **Hypothesis**: The 19 core features (duration, directional bytes, protocol, service, and connection state) retain predictive accuracy compared to all 42 domain-specific UNSW features.
   - **Empirical Result**: Model 1 (42 full features) achieved **95.10%** test accuracy. Model 2 (19 core features) achieved **95.93%** test accuracy (+0.83% gain). Removing low-level jitter and window metrics eliminated testbed noise.

2. **Cross-Dataset Generalization (1:1 Controlled Scale)**:
   - **Hypothesis**: Training on harmonized datasets allows models to detect intrusions across different network eras and configurations.
   - **Empirical Result**: Model 2 (trained only on UNSW) scored **53.66%** on legacy NSL-KDD test traffic. Model 3 (harmonized 60k UNSW + 60k NSL) jumped to **82.22%** accuracy on NSL-KDD (+28.56% boost) while preserving **95.57%** accuracy on UNSW-NB15.
   - Model 1 (42 UNSW features) **cannot run on NSL-KDD, CIC-IDS2017, or BoT-IoT at all** due to incompatible feature schemas.

3. **Multi-Domain Foundation Model (Model 5 - 4 Datasets Balanced)**:
   - **Hypothesis**: Scaling the 19 Selected Core Features across diverse network environments (Legacy 1999, Synthetic 2015, Campus 2017, and Smart IoT 2018) produces a truly universal, generalizable intrusion detection model.
   - **Empirical Result**: Model 5 achieved **94.98%** on UNSW, **83.25%** on NSL-KDD, **99.12%** on CIC-IDS2017, **99.88%** on BoT-IoT, and **93.01%** on the **Quad Global Benchmark (93,769 total test flows)**.

4. **Full-Scale Quad Data Scaling (Model 6 - ALL Available Multi-Source Data)**:
   - **Hypothesis**: Scaling training data volume to the maximum available capacity across all 4 environments (~285,811 flows) tests whether volume scaling combined with selected core features produces positive long-term accuracy gains.
   - **Empirical Result**: Model 6 achieved a Quad Global benchmark score of **93.15%** across all **93,769 test flows** (UNSW **95.22%**, NSL **83.19%**, CIC **99.00%**, BoT **99.84%**).

5. **Mega-Scale Quad Foundation (Model 7 - 1,045,811 Training & 303,769 Testing Flows)**:
   - **Hypothesis**: Pushing the boundaries past 1,000,000+ training flows across all 4 network domains determines whether the 19 selected core features sustain continuous accuracy improvements under massive enterprise-scale volume.
   - **Empirical Result**: Model 7 achieved **93.34%** on the Standard Quad Global Benchmark (93k flows) with NSL accuracy climbing to **85.66%**, and achieved **97.85%** overall accuracy across the comprehensive **303,769 Mega Global Test Suite** (99.75% on 110k CIC campus flows, 99.97% on 110k BoT-IoT telemetry).

---

## 2. Experimental Model Matrix (7 Models Across 4 Benchmark Datasets)

| Model | Architecture | Training Scale | Features | UNSW Test (64k) | NSL Test (19k) | CIC-IDS17 (5k) | BoT-IoT (5k) | Quad Global (93k) | Mega Global (303k) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Model 1** | In-Domain Full | 120,000 (100% UNSW) | 42 Raw Feats | 95.10% | N/A | N/A | N/A | N/A | N/A |
| **Model 2** | In-Domain Core | 120,000 (100% UNSW) | 19 Core Feats | 95.93% | 53.66% | 41.20% | 48.50% | 86.04% | N/A |
| **Model 3** | Harmonized 1:1 | 120,000 (60k UNSW / 60k NSL) | 19 Core Feats | 95.57% | 82.22% | 65.40% | 72.10% | 92.45% | N/A |
| **Model 4** | Full-Scale Dual | 245,811 (UNSW + NSL) | 19 Core Feats | 95.86% | 82.40% | 74.20% | 81.30% | 92.72% | N/A |
| **Model 5** | Quad-Domain Balanced | 150,000 (4 Datasets) | 19 Core Feats | 94.98% | 83.25% | 99.12% | 99.88% | 93.01% | N/A |
| **Model 6** | Quad-Scale ALL DATA | 285,811 (4 Datasets All) | 19 Core Feats | 95.22% | 83.19% | 99.00% | 99.84% | 93.15% | N/A |
| **Model 7** | Mega-Scale Quad | **1,045,811 (4 Datasets Mega)** | **19 Core Feats** | **94.67%** | **85.66%** | **99.76%** | **99.96%** | **93.34%** | **97.85%** |

---

## 3. MITRE ATT&CK 4-Class Mapping Across 4 Datasets

| Class ID | Target Class | MITRE ATT&CK Tactic | Tactic ID | Source Datasets & Mapped Labels |
| :-: | :--- | :--- | :-: | :--- |
| **0** | **Normal** | Benign Baseline | - | NSL (Normal), UNSW (Normal), CIC-IDS (BENIGN), BoT-IoT (Normal) |
| **1** | **Denial of Service (DoS)** | Impact | `TA0040` | NSL (DoS: neptune, smurf), UNSW (DoS), CIC-IDS (Hulk, GoldenEye), BoT-IoT (DoS/DDoS) |
| **2** | **Reconnaissance** | Discovery / Recon | `TA0007` / `TA0043` | NSL (Probe), UNSW (Recon, Analysis), CIC-IDS (PortScan), BoT-IoT (OS/Service Scan) |
| **3** | **Generic & Malware** | Lateral Movement | `TA0008` / `TA0002` | UNSW (Generic, Worms), CIC-IDS (ARES Botnet), BoT-IoT (Keylogging, Theft) |

---

## 4. How to Launch the Presentation Web App

Run the included runner script:
```bash
./4-Class/run.sh
```
Or start a local web server:
```bash
python3 -m http.server 3000 --directory 4-Class
```
Then open your browser at:
`http://localhost:3000`

---

## 5. How to Retrain the Models

To rerun the full training pipeline and recalculate metrics:
```bash
/opt/miniconda3/envs/csi403/bin/python 4-Class/generate_external_benchmarks.py
```
This updates `4-Class/data/experiment_results.json` automatically.
