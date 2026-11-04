#!/usr/bin/env python3
"""Master runner for the four-dataset preparation workflow.

CIC-IDS2017, BoT-IoT, and Borderline-SMOTE processing lives in notebooks;
this runner executes their code cells in order without writing execution
outputs back into the source notebooks. CENTRAL dataset assembly lives in build_dataset.ipynb.
"""

import json
import os
import sys
import time
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / "data-pipeline"
DATASETS_DIR = PIPELINE_DIR / "sub-dataset"


def run_step(step_name, cmd_args, cwd=None):
    print("\n" + "=" * 80)
    print(f"STEP: {step_name}")
    print("Command:", " ".join(str(arg) for arg in cmd_args))
    print("=" * 80)
    started = time.time()
    result = subprocess.run(cmd_args, cwd=cwd or PROJECT_ROOT, check=True)
    print(f"Finished {step_name} in {time.time() - started:.2f}s (Exit code: {result.returncode})")


def run_notebook(step_name, notebook_path, cwd=None, parameters=None):
    notebook_path = Path(notebook_path).resolve()
    working_dir = Path(cwd or notebook_path.parent).resolve()
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    namespace = {"__name__": "__main__", "__file__": str(notebook_path)}
    parameters = parameters or {}

    print("\n" + "=" * 80)
    print(f"STEP: {step_name}")
    print(f"Notebook: {notebook_path}")
    print("=" * 80)
    started = time.time()
    previous_dir = Path.cwd()
    try:
        os.chdir(working_dir)
        parameter_cell_found = not parameters
        for cell_number, cell in enumerate(notebook.get("cells", []), start=1):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source", []))
            tags = cell.get("metadata", {}).get("tags", [])
            exec(compile(source, f"{notebook_path.name}:cell-{cell_number}", "exec"), namespace)
            if "parameters" in tags:
                parameter_cell_found = True
                for key, value in parameters.items():
                    namespace[key] = value
        if not parameter_cell_found:
            raise ValueError(f"Notebook has no cell tagged 'parameters': {notebook_path}")
    except Exception as error:
        raise RuntimeError(f"{step_name} failed while executing {notebook_path.name}") from error
    finally:
        os.chdir(previous_dir)
    print(f"Finished {step_name} in {time.time() - started:.2f}s")


def main():
    print("=" * 80)
    print("QUAD-DOMAIN NETWORK INTRUSION DETECTION PIPELINE BUILDER")
    print("Datasets: NSL-KDD, UNSW-NB15, CIC-IDS2017, BoT-IoT")
    print("CIC/BoT cleansing and harmonization plus SMOTE run from notebooks.")
    print("=" * 80)
    started = time.time()

    for dataset, raw_train, download_label in [
        ("CIC-IDS2017", "CIC_IDS2017_training-set.csv", "CIC-IDS2017"),
        ("BoT-IoT", "BoT_IoT_training-set.csv", "BoT-IoT"),
    ]:
        dataset_dir = DATASETS_DIR / dataset
        if not (dataset_dir / "raw" / raw_train).is_file():
            run_step(f"Prepare {download_label} input files", [sys.executable, "download.py"], cwd=dataset_dir)
        else:
            print(f"\n[OK] {download_label} training input exists.")

        if not (dataset_dir / "output" / "harmonized" / "features.csv").is_file():
            run_notebook(f"{download_label} cleansing", dataset_dir / "cleansing.ipynb", cwd=dataset_dir)
            run_notebook(f"{download_label} harmonization", dataset_dir / "harmonization.ipynb", cwd=dataset_dir)
        else:
            print(f"[OK] {download_label} harmonized output exists.")

    central_dir = PIPELINE_DIR / "CENTRAL"
    run_notebook("Build Central Dataset and splits", central_dir / "build_dataset.ipynb", cwd=central_dir)
    run_notebook(
        "Borderline-SMOTE on train_full",
        central_dir / "borderline_smote.ipynb",
        cwd=central_dir,
        parameters={"SMOTE_SPLIT": "train_full"},
    )
    run_notebook(
        "Borderline-SMOTE on train",
        central_dir / "borderline_smote.ipynb",
        cwd=central_dir,
        parameters={"SMOTE_SPLIT": "train"},
    )
    run_step("Quad-dataset quality audit", [sys.executable, "audit_all_pipelines.py"], cwd=PIPELINE_DIR)

    print("\n" + "=" * 80)
    print(f"ALL STEPS COMPLETED SUCCESSFULLY IN {time.time() - started:.2f}s!")
    print("The prepared splits are in data-pipeline/CENTRAL/output/splits/")
    print("=" * 80)


if __name__ == "__main__":
    main()
