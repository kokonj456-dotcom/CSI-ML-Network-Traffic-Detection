import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
AUTOENCODER_DIR = SCRIPTS_DIR.parent
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]

RESULTS_DIR = AUTOENCODER_DIR / "results"
CSV_DIR = RESULTS_DIR / "csv"
PNG_DIR = RESULTS_DIR / "png"

CSV_DIR.mkdir(parents=True, exist_ok=True)
PNG_DIR.mkdir(parents=True, exist_ok=True)

# Copy base unseen evaluation results if they exist in MODEL_DIR
for name in ["unseen_attack_details.csv", "unseen_attack_results.csv"]:
    src = AUTOENCODER_DIR / name
    dst = CSV_DIR / name
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)

PYTHON_EXE = sys.executable

# ลำดับการรันตาม Dependency
SCRIPTS_TO_RUN = [
    # 1. Data Checks
    SCRIPTS_DIR / "data_checks" / "inspect_attack_samples.py",

    # 2. Analysis
    SCRIPTS_DIR / "analysis" / "analyze_attack_error_totals.py",
    SCRIPTS_DIR / "analysis" / "analyze_error_overlap.py",
    SCRIPTS_DIR / "analysis" / "analyze_feature_comparison.py",
    SCRIPTS_DIR / "analysis" / "analyze_feature_errors.py",
    SCRIPTS_DIR / "analysis" / "analyze_missed_attacks.py",
    SCRIPTS_DIR / "analysis" / "analyze_train_attack_recall.py",
    SCRIPTS_DIR / "analysis" / "analyze_unseen.py",
    SCRIPTS_DIR / "analysis" / "analyze_warezclient_overlap.py",
    SCRIPTS_DIR / "analysis" / "inspect_missed_reconstruction.py",
    SCRIPTS_DIR / "analysis" / "summarize_missed_feature_errors.py",

    # 3. Experiments
    SCRIPTS_DIR / "experiments" / "evaluate_threshold.py",
    SCRIPTS_DIR / "experiments" / "compare_anomaly_scoring.py",
    SCRIPTS_DIR / "experiments" / "compare_feature_subset.py",
    SCRIPTS_DIR / "experiments" / "evaluate_feature_subset_all_attacks.py",
    SCRIPTS_DIR / "experiments" / "compare_missed_features.py",
    SCRIPTS_DIR / "experiments" / "compare_warezclient_features.py",
    SCRIPTS_DIR / "experiments" / "evaluate_topk_scoring.py",
    SCRIPTS_DIR / "experiments" / "compare_topk_difficult_attacks.py",
    SCRIPTS_DIR / "experiments" / "evaluate_hybrid_kddtest.py",
    SCRIPTS_DIR / "experiments" / "validate_anomaly_scoring.py",

    # 4. Visualizations
    SCRIPTS_DIR / "visualization" / "plot_autoencoder_results.py",
    SCRIPTS_DIR / "visualization" / "plot_reconstruction_errors.py",
]


def run_script(script_path: Path):
    rel_path = script_path.relative_to(SCRIPTS_DIR)
    print(f"\n[{rel_path}] กำลังประมวลผล...")
    start_time = time.time()

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [PYTHON_EXE, str(script_path)],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    elapsed = time.time() - start_time

    if result.returncode == 0:
        print(f"[{rel_path}] สำเร็จ ({elapsed:.2f}s)")
        return True, ""
    else:
        print(f"[{rel_path}] เกิดข้อผิดพลาด (exit code {result.returncode})")
        print("--- STDERR ---")
        print(result.stderr[-500:] if result.stderr else "No stderr")
        return False, result.stderr


def main():
    print("=" * 70)
    print("AUTOENCODER LAB - EXECUTE ALL SCRIPTS & SAVE TO RESULTS")
    print(f"Target CSV dir: {CSV_DIR}")
    print(f"Target PNG dir: {PNG_DIR}")
    print("=" * 70)

    success_count = 0
    fail_count = 0
    failed_scripts = []

    for script in SCRIPTS_TO_RUN:
        if not script.exists():
            print(f"[SKIP] ไม่พบไฟล์: {script.name}")
            continue

        ok, err = run_script(script)
        if ok:
            success_count += 1
        else:
            fail_count += 1
            failed_scripts.append(script.name)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"สำเร็จทั้งหมด: {success_count}/{len(SCRIPTS_TO_RUN)} สคริปต์")
    if fail_count > 0:
        print(f"สคริปต์ที่ล้มเหลว ({fail_count}): {', '.join(failed_scripts)}")
    else:
        print("สคริปต์ทั้งหมดทำงานสำเร็จ 100%!")

    # สรุปไฟล์ใน results/
    csv_files = list(CSV_DIR.glob("*.csv"))
    png_files = list(PNG_DIR.glob("*.png"))
    print(f"\nไฟล์ CSV ที่สร้างใน results/csv/ ({len(csv_files)} ไฟล์):")
    for f in sorted(csv_files):
        print(f"  - {f.name} ({f.stat().st_size:,} bytes)")

    print(f"\nไฟล์ PNG ที่สร้างใน results/png/ ({len(png_files)} ไฟล์):")
    for f in sorted(png_files):
        print(f"  - {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
