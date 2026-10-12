"""Load and validate the engineered NSL-KDD model inputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FEATURE_DIR = PROJECT_ROOT / "data-pipeline" / "output" / "NSL-KDD" / "feature_engineered"
OUTPUT_DIR = PROJECT_ROOT / "data-pipeline" / "output" / "NSL-KDD" / "isolation_forest"
SPLITS = ("KDDTrain", "KDDTest", "KDDTest-21")
TARGET_COLUMNS = ("label", "attack_family", "is_attack")
MODEL_FEATURE_KINDS = {"original_numeric", "one_hot"}


def load_inputs() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], pd.DataFrame]:
    """Read features, targets, and schema; keep only the baseline model features."""
    if not FEATURE_DIR.is_dir():
        expected = FEATURE_DIR / "KDDTrain_features.csv"
        raise FileNotFoundError(
            f"Feature files not found: {expected}\n"
            "Run data-pipeline/nsl_cleansing.ipynb, then "
            "data-pipeline/nsl_feature_engineering.ipynb first."
        )

    features = {
        split: pd.read_csv(FEATURE_DIR / f"{split}_features.csv")
        for split in SPLITS
    }
    targets = {
        split: pd.read_csv(FEATURE_DIR / f"{split}_targets.csv")
        for split in SPLITS
    }
    schema = pd.read_csv(FEATURE_DIR / "feature_schema.csv")

    if not {"feature", "kind"}.issubset(schema.columns):
        raise ValueError("feature_schema.csv must contain 'feature' and 'kind' columns.")

    train_columns = features["KDDTrain"].columns.tolist()
    if any(frame.columns.tolist() != train_columns for frame in features.values()):
        raise ValueError("Train, Test, and Test-21 feature columns or order do not match.")

    schema_features = set(schema["feature"].astype(str))
    if set(train_columns) != schema_features:
        raise ValueError("feature_schema.csv does not match the feature CSV columns.")

    model_columns = schema.loc[
        schema["kind"].isin(MODEL_FEATURE_KINDS), "feature"
    ].astype(str).tolist()
    if not model_columns:
        raise ValueError("No baseline model features found in feature_schema.csv.")

    forbidden = set(TARGET_COLUMNS) & set(model_columns)
    if forbidden:
        raise ValueError(f"Target leakage: target columns found in model input: {sorted(forbidden)}")

    for split in SPLITS:
        if len(features[split]) != len(targets[split]):
            raise ValueError(f"Feature/target row count mismatch for {split}.")
        if not {"label", "is_attack"}.issubset(targets[split].columns):
            raise ValueError(f"Target file for {split} must contain label and is_attack.")

    # Engineered alternatives remain available for later ablation, but are not
    # included in this baseline to avoid duplicate or questionable influence.
    features = {split: frame.loc[:, model_columns].copy() for split, frame in features.items()}
    model_schema = schema.loc[schema["feature"].isin(model_columns)].copy()
    return features, targets, model_schema
