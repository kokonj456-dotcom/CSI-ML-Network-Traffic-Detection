#!/usr/bin/env python3
"""
Master Quad-Dataset Build Runner
Executes the full pipeline to prepare the Central Harmonized Dataset and Borderline-SMOTE splits:
1. Generates/verifies CIC-IDS2017 benchmark data
2. Runs CIC-IDS2017 cleansing and harmonization
3. Generates/verifies BoT-IoT benchmark data
4. Runs BoT-IoT cleansing and harmonization
5. Builds Central Harmonized Dataset across all 4 datasets (747,504 flows)
6. Applies Borderline-SMOTE oversampling for Class 4 (R2L) (629,582 flows)
"""

import sys
import time
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "data-pipeline"

def run_step(step_name, cmd_args, cwd=None):
    print("\n" + "=" * 80)
    print(f"STEP: {step_name}")
    print("Command:", " ".join(cmd_args))
    print("=" * 80)
    t0 = time.time()
    res = subprocess.run(cmd_args, cwd=cwd or PROJECT_ROOT, check=True)
    print(f"Finished {step_name} in {time.time() - t0:.2f}s (Exit code: {res.returncode})")

def main():
    py_exec = sys.executable
    print("=" * 80)
    print("QUAD-DOMAIN NETWORK INTRUSION DETECTION PIPELINE BUILDER")
    print("Datasets: NSL-KDD, UNSW-NB15, CIC-IDS2017, BoT-IoT")
    print("Target: 6-Class MITRE ATT&CK Harmonized + Borderline-SMOTE Central Dataset")
    print("=" * 80)

    t_start = time.time()

    # Step 1: CIC-IDS2017 Raw Data Verification
    cic_dir = PIPELINE_DIR / "CIC-IDS2017"
    if not (cic_dir / "raw" / "CIC_IDS2017_training-set.csv").is_file():
        run_step("1. Generate CIC-IDS2017 Benchmark Data", [py_exec, "download.py"], cwd=cic_dir)
    else:
        print("\n[OK] CIC-IDS2017 raw data already exists.")

    # Step 2: CIC-IDS2017 Pipeline
    if not (cic_dir / "output" / "harmonized" / "features.csv").is_file():
        run_step("2. Run CIC-IDS2017 Cleansing & Harmonization", [py_exec, "run_pipeline.py"], cwd=cic_dir)
    else:
        print("[OK] CIC-IDS2017 harmonized output already exists.")

    # Step 3: BoT-IoT Raw Data Verification
    bot_dir = PIPELINE_DIR / "BoT-IoT"
    if not (bot_dir / "raw" / "BoT_IoT_training-set.csv").is_file():
        run_step("3. Generate BoT-IoT Benchmark Data", [py_exec, "download.py"], cwd=bot_dir)
    else:
        print("\n[OK] BoT-IoT raw data already exists.")

    # Step 4: BoT-IoT Pipeline
    if not (bot_dir / "output" / "harmonized" / "features.csv").is_file():
        run_step("4. Run BoT-IoT Cleansing & Harmonization", [py_exec, "run_pipeline.py"], cwd=bot_dir)
    else:
        print("[OK] BoT-IoT harmonized output already exists.")

    # Step 5: Build Central Harmonized Dataset (747k flows)
    central_dir = PIPELINE_DIR / "CENTRAL"
    run_step("5. Build Central Harmonized Dataset & Splits", [py_exec, "build_dataset.py"], cwd=central_dir)

    # Step 6: Apply Borderline-SMOTE
    run_step("6. Apply Borderline-SMOTE to Train Full", [py_exec, "apply_borderline_smote.py", "--split", "train_full", "--target_samples", "40000"], cwd=central_dir)
    run_step("7. Apply Borderline-SMOTE to Train 80%", [py_exec, "apply_borderline_smote.py", "--split", "train", "--target_samples", "40000"], cwd=central_dir)

    # Step 7: Final Audit
    run_step("8. Run Quad-Dataset Quality Audit", [py_exec, "audit_all_pipelines.py"], cwd=PIPELINE_DIR)

    total_time = round(time.time() - t_start, 2)
    print("\n" + "=" * 80)
    print(f"ALL STEPS COMPLETED SUCCESSFULLY IN {total_time}s!")
    print("The harmonized dataset is ready in data-pipeline/CENTRAL/output/splits/")
    print("=" * 80)

if __name__ == "__main__":
    main()

