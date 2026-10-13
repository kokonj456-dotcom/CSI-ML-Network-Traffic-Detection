import sys
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]

DATA_DIR = (
    PROJECT_ROOT
    / "data-pipeline"
    / "output"
    / "NSL-KDD"
    / "feature_engineered"
)

MODEL_DIR = AUTOENCODER_DIR
CSV_DIR = MODEL_DIR / "results" / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

DIFFICULT_LABELS = [
    "snmpguess",
    "snmpgetattack",
    "mailbomb",
]

FEATURES_TO_COMPARE = [
    "same_srv_rate",
    "diff_srv_rate",
    "dst_host_srv_count",
    "dst_host_count",
    "dst_host_rerror_rate",
    "dst_host_serror_rate",
    "srv_diff_host_rate",
    "dst_host_same_srv_rate",
    "log1p_dst_bytes",
    "log1p_total_bytes",
    "signed_log_byte_difference",
    "service=private",
]


def main():
    # 1. โหลด Features และ Targets
    train_features = pd.read_csv(
        DATA_DIR / "KDDTrain_features.csv"
    )
    train_targets = pd.read_csv(
        DATA_DIR / "KDDTrain_targets.csv"
    )

    test_features = pd.read_csv(
        DATA_DIR / "KDDTest_features.csv"
    )
    test_targets = pd.read_csv(
        DATA_DIR / "KDDTest_targets.csv"
    )

    # 2. สร้าง Normal Validation
    normal_mask = train_targets["is_attack"].eq(0)

    _, normal_val = train_test_split(
        train_features.loc[normal_mask],
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    # 3. หา Attack ที่ไม่พบในชุดฝึก
    train_labels = set(
        train_targets.loc[
            train_targets["is_attack"].eq(1), "label"
        ].astype(str).str.strip().str.lower()
    )

    test_labels = (
        test_targets["label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    is_attack = test_targets["is_attack"].eq(1)
    is_unseen = is_attack & ~test_labels.isin(train_labels)

    difficult_mask = (
        is_unseen & test_labels.isin(DIFFICULT_LABELS)
    )

    difficult_attacks = test_features.loc[difficult_mask]

    print("=== Record Count ===")
    print(f"Normal Validation: {len(normal_val)}")
    print(f"Difficult Attacks: {len(difficult_attacks)}")

    # 4. เปรียบเทียบสถิติของฟีเจอร์ที่สนใจ
    summary_rows = []

    for feature in FEATURES_TO_COMPARE:
        if (
            feature in normal_val.columns
            and feature in difficult_attacks.columns
        ):
            normal_values = normal_val[feature]
            attack_values = difficult_attacks[feature]

            summary_rows.append({
                "feature": feature,
                "normal_median": normal_values.median(),
                "attack_median": attack_values.median(),
                "difference": (
                    attack_values.median()
                    - normal_values.median()
                ),
                "normal_mean": normal_values.mean(),
                "attack_mean": attack_values.mean(),
                "normal_q25": normal_values.quantile(0.25),
                "normal_q75": normal_values.quantile(0.75),
                "attack_q25": attack_values.quantile(0.25),
                "attack_q75": attack_values.quantile(0.75),
            })

    # 5. แสดงและบันทึกผล
    results = pd.DataFrame(summary_rows)

    if results.empty:
        print("No matching features were found.")
        return

    print("\n=== Median Comparison ===")
    print(results.round(4).to_string(index=False))

    output_path = CSV_DIR / "missed_feature_comparison.csv"

    results.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"\nSaved report: {output_path}")


if __name__ == "__main__":
    main()
