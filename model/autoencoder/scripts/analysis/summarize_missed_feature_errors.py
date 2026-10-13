from pathlib import Path
import pandas as pd

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = AUTOENCODER_DIR
CSV_DIR = MODEL_DIR / "results" / "csv"

candidates = [
    CSV_DIR / "missed_attack_feature_errors.csv",
    MODEL_DIR / "missed_attack_feature_errors.csv",
]

input_path = next((p for p in candidates if p.exists()), None)

if not input_path:
    raise FileNotFoundError(
        "ไม่พบไฟล์ missed_attack_feature_errors.csv กรุณารัน inspect_missed_reconstruction.py ก่อน"
    )

df = pd.read_csv(input_path)

for label, group in df.groupby("attack_label"):
    group = group.copy()

    # Difference and ratio between missed attacks and Normal.
    group["median_error_diff"] = (
        group["missed_median_error"] - group["normal_median_error"]
    )

    group["median_error_ratio"] = (
        group["missed_median_error"]
        / group["normal_median_error"].replace(0, float("nan"))
    )

    group["mean_error_diff"] = (
        group["missed_mean_error"] - group["normal_mean_error"]
    )

    print("\n" + "=" * 80)
    print(f"Attack: {label}")
    print("=" * 80)

    print("\nTop features with higher median error on missed attacks:")
    print(
        group.sort_values("median_error_diff", ascending=False)[
            [
                "feature",
                "normal_median_error",
                "missed_median_error",
                "median_error_diff",
                "median_error_ratio",
            ]
        ].head(8).round(5).to_string(index=False)
    )

    print("\nTop features with higher mean error on missed attacks:")
    print(
        group.sort_values("mean_error_diff", ascending=False)[
            [
                "feature",
                "normal_mean_error",
                "missed_mean_error",
                "mean_error_diff",
            ]
        ].head(8).round(5).to_string(index=False)
    )
