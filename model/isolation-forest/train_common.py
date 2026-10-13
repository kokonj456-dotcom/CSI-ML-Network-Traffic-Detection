"""Compare Isolation Forest feature profiles on the common NSL-KDD/UNSW data.

Labels are loaded only after predictions are made. They are never used to fit
Isolation Forest, preprocessing, or the alert threshold.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import OneHotEncoder, StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMMON_OUTPUT = PROJECT_ROOT / "data-pipeline" / "common" / "output"
SPLIT_DIR = COMMON_OUTPUT / "splits"
ENGINEERED_DIR = COMMON_OUTPUT / "feature_engineering"
BACKUP_DIR = Path(__file__).resolve().parent / "backup"
SPLITS = ("train", "validation", "test")
RECORD_ID = "record_id"
SOURCE_NAMES = ("NSL-KDD", "UNSW-NB15")

V0_PROTOCOLS = ["tcp", "udp", "icmp", "other"]
V0_NUMERIC_FEATURES = [
    "log_duration",
    "log_bytes_forward",
    "log_bytes_backward",
    "log_total_bytes",
    "log_bytes_ratio",
    "log_bytes_per_second",
]
V0_FEATURES = V0_NUMERIC_FEATURES + [f"protocol_{name}" for name in V0_PROTOCOLS]

FORBIDDEN_MODEL_COLUMNS = {
    RECORD_ID,
    "label",
    "label_raw",
    "label_source_category",
    "attack_category",
    "label_binary",
    "attack_family",
    "is_attack",
    "source_dataset",
    "orig_row_id",
    "data_split",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare common joint_v0/joint_v1 Isolation Forest and test dataset transfer."
    )
    parser.add_argument("--estimators", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--alert-rate", type=float, default=0.05)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.estimators < 1:
        raise ValueError("--estimators must be a positive integer")
    if not 0.0 < args.alert_rate < 0.5:
        raise ValueError("--alert-rate must be greater than 0 and less than 0.5")


def _same_ids(left: pd.Series, right: pd.Series, description: str) -> None:
    left_ids = left.astype("string").reset_index(drop=True)
    right_ids = right.astype("string").reset_index(drop=True)
    if not left_ids.equals(right_ids):
        raise ValueError(f"record_id order does not match for {description}")


def load_inputs() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Load model features and metadata; keep labels separate until scoring is done."""
    raw_features: dict[str, pd.DataFrame] = {}
    metadata: dict[str, pd.DataFrame] = {}
    engineered: dict[str, pd.DataFrame] = {}

    for split in SPLITS:
        raw = pd.read_csv(SPLIT_DIR / split / "features.csv", dtype={RECORD_ID: "string"})
        meta = pd.read_csv(SPLIT_DIR / split / "metadata.csv", dtype={RECORD_ID: "string"})
        ready = pd.read_csv(
            ENGINEERED_DIR / split / "features.csv", dtype={RECORD_ID: "string"}
        )
        if RECORD_ID not in raw or RECORD_ID not in meta or RECORD_ID not in ready:
            raise ValueError(f"{split}: features/metadata missing {RECORD_ID}")
        _same_ids(raw[RECORD_ID], meta[RECORD_ID], f"{split} raw features and metadata")
        _same_ids(raw[RECORD_ID], ready[RECORD_ID], f"{split} raw and joint_v1 features")
        if meta["source_dataset"].isna().any():
            raise ValueError(f"{split}: source_dataset contains missing values")
        raw_features[split] = raw
        metadata[split] = meta
        engineered[split] = ready

    return raw_features, metadata, engineered


def load_labels(split: str, expected_ids: pd.Series) -> pd.DataFrame:
    """Read labels for post-score evaluation, never for model fitting."""
    labels = pd.read_csv(
        SPLIT_DIR / split / "labels.csv",
        dtype={RECORD_ID: "string", "label_raw": "string"},
        low_memory=False,
    )
    expected_ids = expected_ids.astype("string").reset_index(drop=True)
    label_ids = labels[RECORD_ID].astype("string").reset_index(drop=True)
    if len(expected_ids) == len(label_ids):
        _same_ids(expected_ids, label_ids, f"{split} features and labels")
    else:
        # Cross-dataset evaluation scores only one source's rows from the full
        # common Test split. Select matching labels by stable record_id, never
        # by assuming that source rows happen to be at the same offsets.
        if expected_ids.duplicated().any() or label_ids.duplicated().any():
            raise ValueError(f"{split}: duplicate record_id found during label alignment")
        label_positions = pd.Series(np.arange(len(labels)), index=label_ids)
        missing_ids = expected_ids[~expected_ids.isin(label_positions.index)]
        if not missing_ids.empty:
            raise ValueError(
                f"{split}: {len(missing_ids):,} expected record_id values are missing from labels"
            )
        positions = label_positions.loc[expected_ids].to_numpy(dtype=int)
        labels = labels.iloc[positions].reset_index(drop=True)
        _same_ids(expected_ids, labels[RECORD_ID], f"{split} selected features and labels")
    if "label_binary" not in labels:
        raise ValueError(f"{split}: labels.csv missing label_binary")
    if labels["label_binary"].isna().any() or not labels["label_binary"].isin([0, 1]).all():
        raise ValueError(f"{split}: label_binary must contain only 0 and 1")
    return labels


def _model_matrix(frame: pd.DataFrame, feature_names: list[str], split: str) -> pd.DataFrame:
    leaked = FORBIDDEN_MODEL_COLUMNS.intersection(feature_names)
    if leaked:
        raise ValueError(f"{split}: forbidden columns selected for X: {sorted(leaked)}")
    missing = sorted(set(feature_names).difference(frame.columns))
    if missing:
        raise ValueError(f"{split}: required model features missing: {missing}")
    matrix = frame.loc[:, feature_names].astype("float64")
    if matrix.isna().any().any() or not np.isfinite(matrix.to_numpy()).all():
        raise ValueError(f"{split}: model features contain missing or infinite values")
    return matrix


def derive_v0_numeric(frame: pd.DataFrame) -> pd.DataFrame:
    """Reproduce the previous committed joint_v0 formulas exactly."""
    duration = frame["duration"].astype("float64")
    forward = frame["bytes_forward"].astype("float64")
    backward = frame["bytes_backward"].astype("float64")
    return pd.DataFrame(
        {
            "log_duration": np.log1p(duration),
            "log_bytes_forward": np.log1p(forward),
            "log_bytes_backward": np.log1p(backward),
            "log_total_bytes": np.log1p(forward + backward),
            "log_bytes_ratio": np.log1p(forward / (backward + 1.0)),
            "log_bytes_per_second": np.log1p(
                (forward + backward) / np.maximum(duration, 1e-6)
            ),
        },
        index=frame.index,
    )


def fit_v0_preprocessor(train: pd.DataFrame) -> dict[str, Any]:
    numeric = derive_v0_numeric(train)
    scaler = StandardScaler().fit(numeric)
    encoder = OneHotEncoder(
        categories=[V0_PROTOCOLS], handle_unknown="ignore", sparse_output=False
    ).fit(train[["protocol"]].astype("string"))
    return {"scaler": scaler, "encoders": {"protocol": encoder}}


def transform_v0(frame: pd.DataFrame, preprocessor: dict[str, Any], split: str) -> pd.DataFrame:
    numeric = preprocessor["scaler"].transform(derive_v0_numeric(frame))
    protocol = preprocessor["encoders"]["protocol"].transform(
        frame[["protocol"]].astype("string")
    )
    values = np.concatenate([numeric, protocol], axis=1)
    return _model_matrix(pd.DataFrame(values, columns=V0_FEATURES), V0_FEATURES, split)


def derive_v1_numeric(frame: pd.DataFrame) -> pd.DataFrame:
    duration = frame["duration"].astype("float64")
    forward = frame["bytes_forward"].astype("float64")
    backward = frame["bytes_backward"].astype("float64")
    return pd.DataFrame(
        {
            "log_duration": np.log1p(duration),
            "log_bytes_forward": np.log1p(forward),
            "log_bytes_backward": np.log1p(backward),
            "signed_log_bytes_ratio": np.log1p(forward) - np.log1p(backward),
        },
        index=frame.index,
    )


def normalize_categories(
    frame: pd.DataFrame, category_map: dict[str, list[str]], split: str
) -> pd.DataFrame:
    normalized: dict[str, pd.Series] = {}
    for column, vocabulary in category_map.items():
        values = frame[column].astype("string").str.strip().str.lower()
        missing = values.isna() | values.eq("")
        if missing.any():
            raise ValueError(f"{split}: {column} has {int(missing.sum()):,} missing values")
        normalized[column] = values.where(values.isin(vocabulary), "other")
    return pd.DataFrame(normalized, index=frame.index)


def _v1_output_name(
    input_name: str,
    encoded_name: str,
    output_prefixes: dict[str, str],
    aliases: dict[str, dict[str, str]],
) -> str:
    category = encoded_name.removeprefix(input_name + "_")
    category = aliases.get(input_name, {}).get(category, category)
    return f"{output_prefixes[input_name]}_{category}"


def fit_v1_preprocessor(
    train: pd.DataFrame,
    saved_preprocessor: dict[str, Any],
    output_prefixes: dict[str, str],
    aliases: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Fit a fold-local joint_v1 transformer using only this fold's Train rows."""
    category_map = saved_preprocessor["categorical_inputs"]
    numeric = derive_v1_numeric(train)
    scaler = StandardScaler().fit(numeric)
    categories = normalize_categories(train, category_map, "source Train")
    encoders: dict[str, OneHotEncoder] = {}
    groups: dict[str, list[str]] = {}
    for column, vocabulary in category_map.items():
        encoder = OneHotEncoder(
            categories=[vocabulary], handle_unknown="ignore", sparse_output=False
        ).fit(categories[[column]])
        encoders[column] = encoder
        encoded_names = encoder.get_feature_names_out([column]).tolist()
        groups[column] = [
            _v1_output_name(column, name, output_prefixes, aliases)
            for name in encoded_names
        ]
    return {
        "scaler": scaler,
        "encoders": encoders,
        "category_map": category_map,
        "feature_groups": groups,
        "numeric_names": numeric.columns.tolist(),
        "feature_names": numeric.columns.tolist()
        + [name for group in groups.values() for name in group],
    }


def transform_v1(
    frame: pd.DataFrame, preprocessor: dict[str, Any], split: str
) -> pd.DataFrame:
    numeric = preprocessor["scaler"].transform(
        derive_v1_numeric(frame)[preprocessor["numeric_names"]]
    )
    categories = normalize_categories(frame, preprocessor["category_map"], split)
    encoded_blocks = [
        preprocessor["encoders"][column].transform(categories[[column]])
        for column in preprocessor["category_map"]
    ]
    values = np.concatenate([numeric, *encoded_blocks], axis=1)
    matrix = _model_matrix(
        pd.DataFrame(values, columns=preprocessor["feature_names"]),
        preprocessor["feature_names"],
        split,
    )
    for group_name, columns in preprocessor["feature_groups"].items():
        if not np.allclose(matrix[columns].sum(axis=1).to_numpy(), 1.0):
            raise ValueError(f"{split}: one-hot group {group_name} is invalid")
    return matrix


def fit_detector(
    train_matrix: pd.DataFrame, args: argparse.Namespace
) -> tuple[IsolationForest, np.ndarray, float, np.ndarray]:
    model = IsolationForest(
        n_estimators=args.estimators,
        contamination="auto",
        random_state=args.seed,
        n_jobs=-1,
    )
    model.fit(train_matrix.to_numpy(dtype="float32"))
    scores = -model.score_samples(train_matrix.to_numpy(dtype="float32"))
    threshold = float(np.quantile(scores, 1.0 - args.alert_rate))
    return model, scores, threshold, scores >= threshold


def score_detector(
    model: IsolationForest, matrix: pd.DataFrame, threshold: float
) -> tuple[np.ndarray, np.ndarray]:
    scores = -model.score_samples(matrix.to_numpy(dtype="float32"))
    return scores, scores >= threshold


def _metrics(labels: pd.DataFrame, scores: np.ndarray, flagged: np.ndarray) -> dict[str, Any]:
    truth = labels["label_binary"].astype(int).to_numpy()
    tn, fp, fn, tp = (int(value) for value in confusion_matrix(truth, flagged, labels=[0, 1]).ravel())
    both_classes = np.unique(truth).size == 2
    return {
        "rows": int(len(labels)),
        "attack_prevalence": float(truth.mean()),
        "alert_rate": float(flagged.mean()),
        "roc_auc": float(roc_auc_score(truth, scores)) if both_classes else None,
        "average_precision": float(average_precision_score(truth, scores)) if both_classes else None,
        "precision": float(precision_score(truth, flagged, zero_division=0)),
        "recall": float(recall_score(truth, flagged, zero_division=0)),
        "f1": float(f1_score(truth, flagged, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if tn + fp else None,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def evaluate_split(
    split: str,
    expected_ids: pd.Series,
    metadata: pd.DataFrame,
    scores: np.ndarray,
    flagged: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    labels = load_labels(split, expected_ids)
    if len(labels) != len(metadata) or len(scores) != len(labels):
        raise ValueError(f"{split}: label, metadata, and score row counts differ")
    return {
        "split": split,
        "threshold": threshold,
        "overall": _metrics(labels, scores, flagged),
        "by_source_dataset": {
            str(source): _metrics(labels.loc[mask].reset_index(drop=True), scores[mask], flagged[mask])
            for source in SOURCE_NAMES
            if (mask := metadata["source_dataset"].eq(source).to_numpy()).any()
        },
        "attack_category_alert_rate": {
            str(category): {
                "rows": int(mask.sum()),
                "alert_rate": float(flagged[mask].mean()),
            }
            for category in labels["attack_category"].dropna().unique()
            if (mask := labels["attack_category"].eq(category).to_numpy()).any()
        },
    }


def run_profile(
    name: str,
    matrices: dict[str, pd.DataFrame],
    record_ids: dict[str, pd.Series],
    metadata: dict[str, pd.DataFrame],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], IsolationForest, float]:
    model, train_scores, threshold, train_flags = fit_detector(matrices["train"], args)
    scored: dict[str, tuple[np.ndarray, np.ndarray]] = {
        "train": (train_scores, train_flags)
    }
    for split in ("validation", "test"):
        scored[split] = score_detector(model, matrices[split], threshold)

    # Labels are read only after all predictions for this profile are complete.
    report = {
        "feature_count": matrices["train"].shape[1],
        "feature_names": matrices["train"].columns.tolist(),
        "training_rows": len(matrices["train"]),
        "threshold_policy": "95th percentile of training anomaly scores",
        "threshold": threshold,
        "splits": {
            split: evaluate_split(
                split,
                record_ids[split],
                metadata[split],
                scores,
                flags,
                threshold,
            )
            for split, (scores, flags) in scored.items()
        },
    }
    return report, model, threshold


def main() -> None:
    args = parse_args()
    validate_args(args)
    raw, metadata, engineered = load_inputs()

    schema_path = ENGINEERED_DIR / "feature_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("profile_name") != "joint_v1" or schema.get("expected_model_feature_count") != 19:
        raise ValueError("Expected the common Feature Engineering profile joint_v1 (19 features).")
    expected_v1_names = schema["feature_names"]
    saved_preprocessor = joblib.load(ENGINEERED_DIR / "preprocessor.joblib")
    if saved_preprocessor.get("fit_split") != "train":
        raise ValueError("joint_v1 preprocessor must be fit on common Train only")
    if saved_preprocessor.get("model_feature_names") != expected_v1_names:
        raise ValueError("joint_v1 preprocessor feature names do not match feature_schema.json")

    for split in SPLITS:
        if not engineered[split]["record_id"].astype("string").reset_index(drop=True).equals(
            raw[split]["record_id"].astype("string").reset_index(drop=True)
        ):
            raise ValueError(f"{split}: joint_v1 and raw feature rows are not aligned")
        if not set(V0_FEATURES).isdisjoint(FORBIDDEN_MODEL_COLUMNS):
            raise AssertionError("A forbidden column entered the feature profile")

    # Rebuild v0 and fit its scaler/encoder on exactly the same common Train rows.
    v0_preprocessor = fit_v0_preprocessor(raw["train"])
    v0_matrices = {
        split: transform_v0(raw[split], v0_preprocessor, split) for split in SPLITS
    }
    v1_matrices = {
        split: _model_matrix(engineered[split], expected_v1_names, split)
        for split in SPLITS
    }

    v0_report, v0_model, v0_threshold = run_profile(
        "joint_v0",
        v0_matrices,
        {split: raw[split][RECORD_ID] for split in SPLITS},
        metadata,
        args,
    )
    v1_report, v1_model, v1_threshold = run_profile(
        "joint_v1",
        v1_matrices,
        {split: raw[split][RECORD_ID] for split in SPLITS},
        metadata,
        args,
    )

    cross_dataset_reports = []
    for training_source, held_out_source in (
        ("NSL-KDD", "UNSW-NB15"),
        ("UNSW-NB15", "NSL-KDD"),
    ):
        train_mask = metadata["train"]["source_dataset"].eq(training_source).to_numpy()
        test_mask = metadata["test"]["source_dataset"].eq(held_out_source).to_numpy()
        fold_preprocessor = fit_v1_preprocessor(
            raw["train"].loc[train_mask].reset_index(drop=True),
            saved_preprocessor,
            schema["categorical_output_prefixes"],
            schema["categorical_output_category_aliases"],
        )
        if fold_preprocessor["feature_names"] != expected_v1_names:
            raise ValueError("Source-only joint_v1 preprocessing changed the feature schema")
        source_train = transform_v1(
            raw["train"].loc[train_mask].reset_index(drop=True),
            fold_preprocessor,
            f"{training_source} train",
        )
        held_out_test = transform_v1(
            raw["test"].loc[test_mask].reset_index(drop=True),
            fold_preprocessor,
            f"{held_out_source} test",
        )
        fold_model, train_scores, threshold, _ = fit_detector(source_train, args)
        test_scores, test_flags = score_detector(fold_model, held_out_test, threshold)
        test_ids = raw["test"].loc[test_mask, RECORD_ID].reset_index(drop=True)
        test_metadata = metadata["test"].loc[test_mask].reset_index(drop=True)
        target_metrics = evaluate_split(
            "test", test_ids, test_metadata, test_scores, test_flags, threshold
        )
        cross_dataset_reports.append(
            {
                "training_dataset": training_source,
                "held_out_test_dataset": held_out_source,
                "training_rows": int(train_mask.sum()),
                "test_rows": int(test_mask.sum()),
                "preprocessor_fit_on": f"{training_source} train only",
                "threshold_policy": "95th percentile of source training anomaly scores",
                "train_threshold": threshold,
                "evaluation": target_metrics,
            }
        )

    # Summarize train contamination only after all fitting/scoring is complete.
    train_labels = load_labels("train", raw["train"][RECORD_ID])
    train_mix = {}
    for source in SOURCE_NAMES:
        mask = metadata["train"]["source_dataset"].eq(source).to_numpy()
        source_labels = train_labels.loc[mask, "label_binary"].astype(int)
        train_mix[source] = {
            "rows": int(mask.sum()),
            "known_attack_rows_for_posthoc_context": int(source_labels.sum()),
            "known_attack_fraction_for_posthoc_context": float(source_labels.mean()),
        }

    created_at = datetime.now().astimezone()
    run_id = (
        "isolation-forest-common-joint-v1-iso-"
        + created_at.strftime("%Y%m%d-%H%M%S-%f")
    )
    model_path = BACKUP_DIR / f"{run_id}.joblib"
    result_path = BACKUP_DIR / f"{run_id}-result.json"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    run_config = {
        "algorithm": "IsolationForest",
        "profile": "common joint_v1",
        "fit_uses_labels": False,
        "training_split": "common train",
        "training_rows": len(v1_matrices["train"]),
        "feature_names": expected_v1_names,
        "n_estimators": args.estimators,
        "contamination": "auto",
        "threshold_policy": "training-score quantile",
        "alert_rate": args.alert_rate,
        "random_seed": args.seed,
    }
    joblib.dump(
        {
            "algorithm": "IsolationForest",
            "model": v1_model,
            "preprocessor": saved_preprocessor,
            "feature_schema": schema,
            "threshold_anomaly_score": v1_threshold,
            "run_config": run_config,
        },
        model_path,
    )
    result = {
        "run_id": run_id,
        "created_at": created_at.isoformat(timespec="microseconds"),
        "parameters": run_config,
        "evaluation_policy": {
            "labels_used_for_fit_or_threshold": False,
            "threshold_uses_test_labels": False,
            "score_direction": "higher means more anomalous",
        },
        "training_label_mix_posthoc_only": train_mix,
        "feature_comparison": {"joint_v0": v0_report, "joint_v1": v1_report},
        "cross_dataset_joint_v1": cross_dataset_reports,
        "artifacts": {"model_file": model_path.name, "result_file": result_path.name},
    }
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    print("\\nIn-domain profile comparison (metrics are post-score only):")
    rows = []
    for profile_name, report in (("joint_v0", v0_report), ("joint_v1", v1_report)):
        for split, summary in report["splits"].items():
            for scope, metrics in [("all", summary["overall"])] + list(
                summary["by_source_dataset"].items()
            ):
                rows.append(
                    {
                        "profile": profile_name,
                        "split": split,
                        "source": scope,
                        **{key: metrics[key] for key in (
                            "alert_rate", "roc_auc", "average_precision", "precision",
                            "recall", "f1", "false_positive_rate"
                        )},
                    }
                )
    print(pd.DataFrame(rows).to_string(index=False))
    print("\\nCross-dataset joint_v1 evaluation:")
    for fold in cross_dataset_reports:
        print(
            f"{fold['training_dataset']} -> {fold['held_out_test_dataset']}: "
            f"{json.dumps(fold['evaluation']['overall'], ensure_ascii=False)}"
        )
    print("\\nSaved joint_v1 model:", model_path)
    print("Saved evaluation:", result_path)


if __name__ == "__main__":
    main()
