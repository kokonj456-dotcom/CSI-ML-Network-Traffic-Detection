# 4-Class Threat Taxonomy & Cross-Dataset Harmonization Study

This folder contains the complete code, trained experiment results, and standalone presentation web dashboard for the **4-Class Network Threat Taxonomy & Cross-Dataset Harmonization Study**.

---

## 1. Research Hypotheses & Key Findings

1. **Feature Pruning & Predictive Retention**:
   - **Hypothesis**: The 19 core features (duration, directional bytes, protocol, service, and connection state) retain predictive accuracy compared to all 42 domain-specific UNSW features.
   - **Empirical Result**: Model 1 (42 full features) achieved **95.10%** test accuracy. Model 2 (19 core features) achieved **95.93%** test accuracy (+0.83% gain). Removing low-level jitter and window metrics eliminated testbed noise.

2. **Cross-Dataset Generalization**:
   - **Hypothesis**: Training on harmonized datasets allows models to detect intrusions across different network eras and configurations.
   - **Empirical Result**: Model 2 (trained only on UNSW) scored **53.66%** on legacy NSL-KDD test traffic. Model 3 (harmonized 60k UNSW + 60k NSL) jumped to **82.22%** accuracy on NSL-KDD (+28.56% boost) while preserving **95.57%** accuracy on UNSW-NB15.
   - Model 1 (42 UNSW features) **cannot run on NSL-KDD at all** due to incompatible feature schemas.

3. **Controlled 1:1 Scale (120,000 Rows Each)**:
   - Dataset 1 (UNSW Alone): 120,000 rows (100% UNSW-NB15).
   - Dataset 2 (Harmonized): 120,000 rows (50% UNSW-NB15 / 50% NSL-KDD).

---

## 2. MITRE ATT&CK 4-Class Mapping

| Class ID | Target Class | MITRE ATT&CK Tactic | Tactic ID | Core Techniques | Source Mappings |
| :-: | :--- | :--- | :-: | :--- | :--- |
| **0** | **Normal** | Benign Baseline | - | Standard interactive network operations | NSL-KDD (Normal) + UNSW (Normal) |
| **1** | **Denial of Service (DoS)** | Impact | `TA0040` | T1498 (Network Flooding), T1499 (Endpoint DoS) | NSL-KDD (DoS) + UNSW (DoS) |
| **2** | **Reconnaissance** | Discovery / Recon | `TA0007` / `TA0043` | T1046 (Network Service Discovery), T1595 (Active Scanning) | NSL-KDD (Probe) + UNSW (Recon, Analysis) |
| **3** | **Generic & Malware** | Lateral Movement | `TA0008` / `TA0002` | T1210 (Exploitation of Remote Services), T1071 (Tooling) | UNSW-NB15 (Generic, Worms) |

---

## 3. How to Launch the Presentation Web App

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

## 4. How to Retrain the Models

To rerun the full training pipeline and recalculate metrics:
```bash
/opt/miniconda3/envs/csi403/bin/python 4-Class/train_experiments.py
```
This updates `4-Class/data/experiment_results.json` automatically.

