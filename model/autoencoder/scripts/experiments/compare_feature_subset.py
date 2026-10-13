import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split

# --------------------------------------------------
# 1. Paths and settings
# --------------------------------------------------
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

FEATURES_PATH = DATA_DIR / "KDDTrain_features.csv"
TARGETS_PATH = DATA_DIR / "KDDTrain_targets.csv"

MODEL_PATH = MODEL_DIR / "autoencoder.pth"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
COLUMNS_PATH = MODEL_DIR / "feature_columns.txt"

RANDOM_STATE = 42

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


# --------------------------------------------------
# 2. Load data and saved artifacts
# --------------------------------------------------
device = torch.device("cpu")

X = pd.read_csv(FEATURES_PATH)
y = pd.read_csv(TARGETS_PATH)

with open(COLUMNS_PATH, "r", encoding="utf-8") as f:
    feature_columns = [line.strip() for line in f if line.strip()]

# Filter SELECTED_FEATURES to only those present in feature_columns
selected_features_filtered = [f for f in SELECTED_FEATURES if f in feature_columns]

X = X[feature_columns]

scaler = joblib.load(SCALER_PATH)

# Reproduce the exact Normal Validation split used during training.
normal_mask = y["is_attack"] == 0
X_normal = X[normal_mask]
y_normal = y[normal_mask]

X_train_norm, X_val_norm, _, _ = train_test_split(
    X_normal,
    y_normal,
    test_size=0.20,
    random_state=RANDOM_STATE,
    shuffle=True,
)

# Attacks from KDDTrain (for development diagnosis only)
attack_mask = y["is_attack"] == 1
X_attack = X[attack_mask]
attack_labels = y.loc[attack_mask, "label"].astype(str).str.strip().str.lower()
attack_families = y.loc[attack_mask, "attack_family"].astype(str).str.strip()

print(f"Normal Validation records: {len(X_val_norm):,}")
print(f"KDDTrain Attack records:   {len(X_attack):,}")
print(f"Features:                  {len(feature_columns)}")


# --------------------------------------------------
# 3. Indices for selected features
# --------------------------------------------------
selected_indices = [
    feature_columns.index(name) for name in selected_features_filtered
]


# --------------------------------------------------
# 4. Model inference
# --------------------------------------------------
model = Autoencoder(input_dim=len(feature_columns)).to(device)
model.load_state_dict(
    torch.load(MODEL_PATH, map_location=device, weights_only=True)
)
model.eval()


def get_reconstruction_errors(df: pd.DataFrame) -> np.ndarray:
    scaled = scaler.transform(df)
    tensor = torch.as_tensor(scaled, dtype=torch.float32, device=device)

    with torch.no_grad():
        reconstructed = model(tensor).cpu().numpy()

    return np.square(scaled - reconstructed)


val_errors = get_reconstruction_errors(X_val_norm)
attack_errors = get_reconstruction_errors(X_attack)


# --------------------------------------------------
# 5. Define scoring methods
# --------------------------------------------------
def score_all_mean(errors: np.ndarray) -> np.ndarray:
    return errors.mean(axis=1)


def score_top_k(errors: np.ndarray, k: int) -> np.ndarray:
    return np.sort(errors, axis=1)[:, -k:].mean(axis=1)


def score_selected(errors: np.ndarray) -> np.ndarray:
    return errors[:, selected_indices].mean(axis=1)


def score_selected_max(errors: np.ndarray) -> np.ndarray:
    return errors[:, selected_indices].max(axis=1)


scoring_methods = {
    "A) Baseline: all features": (
        score_all_mean(val_errors),
        score_all_mean(attack_errors),
    ),
    "B) Top-5 all features": (
        score_top_k(val_errors, 5),
        score_top_k(attack_errors, 5),
    ),
    "C) Top-10 all features": (
        score_top_k(val_errors, 10),
        score_top_k(attack_errors, 10),
    ),
    "D) 10 selected features": (
        score_selected(val_errors),
        score_selected(attack_errors),
    ),
    "E) Max of 10 selected": (
        score_selected_max(val_errors),
        score_selected_max(attack_errors),
    ),
}


# --------------------------------------------------
# 6. Evaluate scoring methods
# --------------------------------------------------
def evaluate_score(method_name: str, val_scores: np.ndarray, attack_scores: np.ndarray):
    print(f"\n{method_name}")
    print("-" * 60)

    for p in (90, 95):
        threshold = np.percentile(val_scores, p)
        pred = attack_scores > threshold

        fpr = np.mean(val_scores > threshold)
        overall_recall = pred.mean()

        warez_mask = attack_labels == "warezclient"
        warez_recall = pred[warez_mask].mean()
        warez_detected = pred[warez_mask].sum()
        warez_total = warez_mask.sum()

        other_recall = pred[~warez_mask].mean()
        other_detected = pred[~warez_mask].sum()
        other_total = (~warez_mask).sum()

        print(
            f"  P{p:02d} threshold={threshold:10.5f} | "
            f"Val FPR={fpr:6.2%} | "
            f"All Attack Recall={overall_recall:6.2%} | "
            f"warezclient={warez_recall:6.2%} ({warez_detected}/{warez_total}) | "
            f"Other Attacks={other_recall:6.2%} ({other_detected}/{other_total})"
        )


print("\n" + "=" * 70)
print("EVALUATION ON KDDTrain ATTACKS (DEVELOPMENT CHECK)")
print("=" * 70)

for name, (val_s, att_s) in scoring_methods.items():
    evaluate_score(name, val_s, att_s)


# --------------------------------------------------
# Per-family recall breakdown
# --------------------------------------------------
results = []

for method_name, (val_s, att_s) in scoring_methods.items():
    for p in (90, 95):
        threshold = np.percentile(val_s, p)
        pred = att_s > threshold

        for family in sorted(attack_families.unique()):
            mask = attack_families == family
            total = mask.sum()
            detected = pred[mask].sum()
            recall = detected / total if total else 0.0

            results.append({
                "method": method_name,
                "threshold": f"P{p}",
                "attack_family": family,
                "total": total,
                "detected": detected,
                "recall": recall,
            })

result_df = pd.DataFrame(results)

print("\n" + "=" * 70)
print("RECALL BY ATTACK FAMILY")
print("=" * 70)

for percentile in ("P90", "P95"):
    print(f"\n--- {percentile} ---")
    table = result_df[result_df["threshold"] == percentile]
    pivot = table.pivot(
        index="attack_family",
        columns="method",
        values="recall",
    )
    print((pivot * 100).round(2).to_string())

output_path = CSV_DIR / "feature_subset_attack_results.csv"
result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
print(f"\nSaved per-family results to: {output_path}")
