import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
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
RESULTS_DIR = MODEL_DIR / "results"
CSV_DIR = RESULTS_DIR / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder

DIFFICULT_LABELS = ["snmpguess", "snmpgetattack", "mailbomb"]

FEATURES_TO_INSPECT = [
    "dst_host_rerror_rate",
    "dst_host_same_srv_rate",
    "signed_log_byte_difference",
    "log1p_dst_bytes",
    "log1p_total_bytes",
    "dst_host_count",
    "dst_host_srv_count",
    "service=private",
    "same_srv_rate",
    "diff_srv_rate",
    "dst_host_serror_rate",
    "srv_diff_host_rate",
]


def main():
    device = torch.device("cpu")

    train_x = pd.read_csv(DATA_DIR / "KDDTrain_features.csv")
    train_y = pd.read_csv(DATA_DIR / "KDDTrain_targets.csv")
    test_x = pd.read_csv(DATA_DIR / "KDDTest_features.csv")
    test_y = pd.read_csv(DATA_DIR / "KDDTest_targets.csv")

    with open(
        MODEL_DIR / "feature_columns.txt",
        "r",
        encoding="utf-8",
    ) as f:
        feature_columns = [line.strip() for line in f if line.strip()]

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    # Reproduce the same Normal Validation split.
    normal_mask = train_y["is_attack"].eq(0).to_numpy()

    _, normal_val = train_test_split(
        train_x.loc[normal_mask],
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    normal_val = normal_val[feature_columns]

    model = Autoencoder(input_dim=len(feature_columns)).to(device)
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location=device,
            weights_only=True,
        )
    )
    model.eval()

    def calculate_feature_errors(data, batch_size=1024):
        scaled = scaler.transform(data[feature_columns])
        batches = []

        with torch.no_grad():
            for start in range(0, len(scaled), batch_size):
                batch = torch.as_tensor(
                    scaled[start : start + batch_size],
                    dtype=torch.float32,
                    device=device,
                )
                reconstructed = model(batch).cpu().numpy()
                original = scaled[start : start + batch_size]
                batches.append(np.square(original - reconstructed))

        return np.concatenate(batches, axis=0)

    normal_errors = calculate_feature_errors(normal_val)
    normal_scores = normal_errors.mean(axis=1)

    threshold = float(np.percentile(normal_scores, 95))

    # Determine unseen-by-label attacks.
    train_labels = (
        train_y["label"].astype(str).str.strip().str.lower()
    )
    test_labels = (
        test_y["label"].astype(str).str.strip().str.lower()
    )

    known_labels = set(
        train_labels[train_y["is_attack"].eq(1)]
    )

    unseen_mask = (
        test_y["is_attack"].eq(1)
        & ~test_labels.isin(known_labels)
    ).to_numpy()

    summary_rows = []
    feature_rows = []

    print("=== Missed Attack Reconstruction Analysis ===")
    print(f"Threshold (P95): {threshold:.6f}")
    print(f"Normal validation records: {len(normal_val)}")
    print(
        f"Normal validation FPR at this threshold: "
        f"{np.mean(normal_scores > threshold):.4%}"
    )

    for label in DIFFICULT_LABELS:
        label_mask = (
            unseen_mask
            & test_labels.eq(label).to_numpy()
        )

        attack_x = test_x.loc[label_mask, feature_columns]

        if attack_x.empty:
            print(f"\nNo records found for {label}")
            continue

        attack_errors = calculate_feature_errors(attack_x)
        attack_scores = attack_errors.mean(axis=1)

        missed_mask = attack_scores <= threshold
        detected_mask = ~missed_mask

        total = len(attack_scores)
        missed = int(missed_mask.sum())
        detected = int(detected_mask.sum())

        summary_rows.append({
            "attack_label": label,
            "total_records": total,
            "missed_records": missed,
            "detected_records": detected,
            "missed_rate": missed / total if total else 0.0,
            "recall": detected / total if total else 0.0,
            "mean_score_all": float(np.mean(attack_scores)),
            "mean_score_missed": (
                float(np.mean(attack_scores[missed_mask]))
                if missed
                else np.nan
            ),
            "median_score_missed": (
                float(np.median(attack_scores[missed_mask]))
                if missed
                else np.nan
            ),
        })

        print(f"\n--- {label} ---")
        print(f"Total: {total} | Missed: {missed} ({missed / total:.2%})")

        # Feature errors for missed records vs Normal validation.
        missed_feature_errors = attack_errors[missed_mask]

        for feature in FEATURES_TO_INSPECT:
            if feature not in feature_columns:
                continue

            idx = feature_columns.index(feature)

            normal_feat = normal_errors[:, idx]
            missed_feat = (
                missed_feature_errors[:, idx]
                if missed
                else np.array([])
            )
            detected_feat = (
                attack_errors[detected_mask, idx]
                if detected
                else np.array([])
            )

            feature_rows.append({
                "attack_label": label,
                "feature": feature,
                "normal_mean_error": float(np.mean(normal_feat)),
                "normal_median_error": float(np.median(normal_feat)),
                "normal_p90_error": float(np.percentile(normal_feat, 90)),
                "normal_p95_error": float(np.percentile(normal_feat, 95)),
                "missed_mean_error": (
                    float(np.mean(missed_feat))
                    if missed else np.nan
                ),
                "missed_median_error": (
                    float(np.median(missed_feat))
                    if missed else np.nan
                ),
                "missed_p90_error": (
                    float(np.percentile(missed_feat, 90))
                    if missed else np.nan
                ),
                "detected_mean_error": (
                    float(np.mean(detected_feat))
                    if detected else np.nan
                ),
            })

    summary_df = pd.DataFrame(summary_rows)
    feature_df = pd.DataFrame(feature_rows)

    summary_path = CSV_DIR / "missed_attack_summary.csv"
    feature_path = CSV_DIR / "missed_attack_feature_errors.csv"

    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    feature_df.to_csv(feature_path, index=False, encoding="utf-8-sig")

    print("\n=== Summary ===")
    if not summary_df.empty:
        print(summary_df.round(4).to_string(index=False))

    print(f"\nSaved summary: {summary_path}")
    print(f"Saved feature analysis: {feature_path}")
    print("\nAnalysis complete.")


if __name__ == "__main__":
    main()
