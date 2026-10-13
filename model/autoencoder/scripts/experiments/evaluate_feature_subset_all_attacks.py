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
CSV_DIR = MODEL_DIR / "results" / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder

SELECTED_FEATURES = [
    "dst_host_same_src_port_rate",
    "host_service_rate_gap",
    "dst_host_same_srv_rate",
    "log1p_dst_host_count",
    "dst_host_srv_diff_host_rate",
    "dst_host_count",
    "logged_in",
    "dst_host_diff_srv_rate",
    "log1p_src_bytes",
    "log1p_dst_host_srv_count",
]


def main():
    device = torch.device("cpu")

    X = pd.read_csv(DATA_DIR / "KDDTrain_features.csv")
    y = pd.read_csv(DATA_DIR / "KDDTrain_targets.csv")

    with open(MODEL_DIR / "feature_columns.txt", "r", encoding="utf-8") as f:
        feature_columns = [line.strip() for line in f if line.strip()]

    selected_features_filtered = [f for f in SELECTED_FEATURES if f in feature_columns]
    selected_indices = [feature_columns.index(f) for f in selected_features_filtered]

    X = X[feature_columns]
    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    normal_mask = y["is_attack"] == 0
    X_train_norm, X_val_norm, _, _ = train_test_split(
        X[normal_mask],
        y[normal_mask],
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    attack_mask = y["is_attack"] == 1
    X_attack = X[attack_mask]
    attack_labels = y.loc[attack_mask, "label"].astype(str).str.strip().str.lower()
    attack_families = y.loc[attack_mask, "attack_family"].astype(str).str.strip()

    model = Autoencoder(input_dim=len(feature_columns)).to(device)
    model.load_state_dict(
        torch.load(MODEL_DIR / "autoencoder.pth", map_location=device, weights_only=True)
    )
    model.eval()

    def get_errors(df):
        scaled = scaler.transform(df)
        tensor = torch.as_tensor(scaled, dtype=torch.float32, device=device)
        with torch.no_grad():
            rec = model(tensor).cpu().numpy()
        return np.square(scaled - rec)

    val_errors = get_errors(X_val_norm)
    attack_errors = get_errors(X_attack)

    val_base = val_errors.mean(axis=1)
    attack_base = attack_errors.mean(axis=1)

    val_sel = val_errors[:, selected_indices].mean(axis=1) if selected_indices else val_base
    attack_sel = attack_errors[:, selected_indices].mean(axis=1) if selected_indices else attack_base

    methods = {
        "Baseline (all features)": (val_base, attack_base),
        "10 Selected Features": (val_sel, attack_sel),
    }

    results = []
    print("=== Feature Subset Diagnostic on All KDDTrain Attacks ===")
    for method_name, (val_s, att_s) in methods.items():
        for p in (90, 95):
            threshold = float(np.percentile(val_s, p))
            pred = att_s > threshold
            overall_recall = float(pred.mean())

            for family in sorted(attack_families.unique()):
                mask = attack_families == family
                total = int(mask.sum())
                detected = int(pred[mask].sum())
                recall = detected / total if total else 0.0

                results.append({
                    "method": method_name,
                    "threshold_percentile": f"P{p}",
                    "threshold": threshold,
                    "attack_family": family,
                    "total": total,
                    "detected": detected,
                    "recall": recall,
                    "overall_recall": overall_recall,
                })

    df = pd.DataFrame(results)
    output_path = CSV_DIR / "feature_subset_all_attacks.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(df.to_string(index=False))
    print(f"\nSaved results: {output_path}")


if __name__ == "__main__":
    main()
