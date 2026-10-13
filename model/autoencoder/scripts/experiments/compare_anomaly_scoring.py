import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]
DATA = PROJECT_ROOT / "data-pipeline" / "output" / "NSL-KDD" / "feature_engineered"
MODEL_DIR = AUTOENCODER_DIR
CSV_DIR = MODEL_DIR / "results" / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder

LABELS = ["snmpguess", "snmpgetattack", "mailbomb"]
PERCENTILES = [90, 95]


def main():
    train_x = pd.read_csv(DATA / "KDDTrain_features.csv")
    train_y = pd.read_csv(DATA / "KDDTrain_targets.csv")
    test_x = pd.read_csv(DATA / "KDDTest_features.csv")
    test_y = pd.read_csv(DATA / "KDDTest_targets.csv")

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    with open(MODEL_DIR / "feature_columns.txt", encoding="utf-8") as f:
        columns = [line.strip() for line in f if line.strip()]

    model = Autoencoder(input_dim=len(columns))
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location="cpu",
            weights_only=True,
        )
    )
    model.eval()

    def get_scores(df):
        # Preserve feature names for StandardScaler
        scaled = scaler.transform(df[columns])
        tensor = torch.tensor(scaled, dtype=torch.float32)

        with torch.no_grad():
            reconstructed = model(tensor).numpy()

        squared_errors = (scaled - reconstructed) ** 2

        return {
            "MSE": squared_errors.mean(axis=1),
            "Top5_Mean": np.sort(
                squared_errors, axis=1
            )[:, -5:].mean(axis=1),
            "Top10_Mean": np.sort(
                squared_errors, axis=1
            )[:, -10:].mean(axis=1),
            "Max_Error": squared_errors.max(axis=1),
        }

    normal_x = train_x.loc[train_y["is_attack"].eq(0)]
    _, normal_val = train_test_split(
        normal_x,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    val_scores = get_scores(normal_val)

    # Calculate threshold for each scoring method
    thresholds = {}
    for method, scores in val_scores.items():
        thresholds[method] = {
            f"P{p}": np.percentile(scores, p)
            for p in PERCENTILES
        }

    test_labels = (
        test_y["label"].astype(str).str.strip().str.lower()
    )
    is_attack = test_y["is_attack"].eq(1)

    # Ground truth: attack labels found in training set
    known_labels = set(
        train_y.loc[
            train_y["is_attack"].eq(1), "label"
        ].astype(str).str.strip().str.lower()
    )

    unseen_mask = is_attack & ~test_labels.isin(known_labels)

    rows = []

    # 1. Normal validation false positive rate check
    for method, scores in val_scores.items():
        for p in PERCENTILES:
            t = thresholds[method][f"P{p}"]
            fpr = (scores > t).mean()

            rows.append({
                "group": "Normal Validation",
                "method": method,
                "percentile": f"P{p}",
                "threshold": t,
                "total": len(scores),
                "flagged": int((scores > t).sum()),
                "rate": fpr,
            })

    # 2. Overall test attacks recall
    attack_scores = get_scores(test_x.loc[is_attack])
    for method, scores in attack_scores.items():
        for p in PERCENTILES:
            t = thresholds[method][f"P{p}"]
            recall = (scores > t).mean()

            rows.append({
                "group": "All Test Attacks",
                "method": method,
                "percentile": f"P{p}",
                "threshold": t,
                "total": len(scores),
                "flagged": int((scores > t).sum()),
                "recall": recall,
            })

    # 3. All unseen test attacks recall
    unseen_scores = get_scores(test_x.loc[unseen_mask])
    for method, scores in unseen_scores.items():
        for p in PERCENTILES:
            t = thresholds[method][f"P{p}"]
            recall = (scores > t).mean()

            rows.append({
                "group": "All Unseen Attacks",
                "method": method,
                "percentile": f"P{p}",
                "threshold": t,
                "total": len(scores),
                "flagged": int((scores > t).sum()),
                "recall": recall,
            })

    # 4. Individual difficult attack labels
    for label in LABELS:
        mask = is_attack & test_labels.eq(label)
        subset = test_x.loc[mask]

        if subset.empty:
            continue

        label_scores = get_scores(subset)

        for method, scores in label_scores.items():
            for p in PERCENTILES:
                t = thresholds[method][f"P{p}"]
                detected = int((scores > t).sum())
                recall = detected / len(scores)

                rows.append({
                    "group": f"Unseen: {label}",
                    "method": method,
                    "percentile": f"P{p}",
                    "threshold": t,
                    "total": len(scores),
                    "flagged": detected,
                    "recall": recall,
                })

    df = pd.DataFrame(rows)

    print("=== Recall comparison by scoring method ===")
    for p in PERCENTILES:
        print(f"\n--- P{p} Threshold ---")
        pivot = df[df["percentile"] == f"P{p}"].pivot(
            index="group",
            columns="method",
            values="recall",
        )
        print((pivot * 100).round(2).to_string())

    output = CSV_DIR / "anomaly_scoring_comparison.csv"
    pd.DataFrame(rows).to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\nSaved results to: {output}")


if __name__ == "__main__":
    main()
