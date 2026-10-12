"""Training and scoring orchestration for the Isolation Forest experiment."""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest

from data import OUTPUT_DIR, load_inputs
from evaluation import evaluate_predictions
from preprocessing import MixedFeatureClusterer
from reporting import (
    write_cluster_profiles,
    write_run_config,
    write_scored_split,
    write_training_results,
)


def validate_args(args: argparse.Namespace) -> None:
    if not 0.0 < args.alert_rate < 0.5:
        raise ValueError("--alert-rate must be greater than 0 and less than 0.5.")
    if args.clusters < 1 or args.estimators < 1:
        raise ValueError("--clusters and --estimators must be positive integers.")


def as_finite_array(features: pd.DataFrame, split: str) -> np.ndarray:
    values = features.to_numpy(dtype=np.float32, copy=True)
    if not np.isfinite(values).all():
        raise ValueError(f"{split} model features contain NaN or infinite values.")
    return values


def fit_anomaly_detector(
    train_features: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[IsolationForest, np.ndarray, float, np.ndarray]:
    """Fit IF on unlabeled training features and derive its alert threshold."""
    train_array = as_finite_array(train_features, "KDDTrain")
    model = IsolationForest(
        n_estimators=args.estimators,
        contamination="auto",
        random_state=args.seed,
        n_jobs=-1,
    )
    model.fit(train_array)  # Labels and targets are deliberately not passed to fit.

    # score_samples is lower for more abnormal records; invert for readability.
    scores = -model.score_samples(train_array)
    threshold = float(np.quantile(scores, 1.0 - args.alert_rate))
    flagged = scores >= threshold
    if not flagged.any():
        raise RuntimeError("No training records were flagged; check the selected alert rate.")
    return model, scores, threshold, flagged


def fit_alert_clusterer(
    train_features: pd.DataFrame,
    feature_schema: pd.DataFrame,
    flagged: np.ndarray,
    args: argparse.Namespace,
) -> tuple[MixedFeatureClusterer, KMeans, int]:
    """Fit K-Means only on flagged KDDTrain records, using cluster-specific scaling."""
    clusterer = MixedFeatureClusterer(feature_schema)
    alert_matrix = clusterer.fit_transform(train_features.loc[flagged])
    actual_clusters = min(args.clusters, len(alert_matrix))
    cluster_model = KMeans(
        n_clusters=actual_clusters,
        n_init=10,
        random_state=args.seed,
    )
    cluster_model.fit(alert_matrix)
    return clusterer, cluster_model, actual_clusters


def score_split(
    model: IsolationForest,
    clusterer: MixedFeatureClusterer,
    cluster_model: KMeans,
    features: pd.DataFrame,
    split: str,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Score a split and assign cluster IDs only to records above threshold."""
    feature_array = as_finite_array(features, split)
    scores = -model.score_samples(feature_array)
    flagged = scores >= threshold
    cluster_ids = np.full(len(features), -1, dtype=int)
    if flagged.any():
        cluster_matrix = clusterer.transform(features.loc[flagged])
        cluster_ids[flagged] = cluster_model.predict(cluster_matrix)
    return scores, flagged, cluster_ids


def run_training(args: argparse.Namespace) -> None:
    """Run the complete experiment and write its artifacts to the configured path."""
    validate_args(args)
    features, targets, model_schema = load_inputs()
    train_features = features["KDDTrain"]

    model, train_scores, threshold, train_flagged = fit_anomaly_detector(
        train_features, args
    )
    clusterer, cluster_model, actual_clusters = fit_alert_clusterer(
        train_features, model_schema, train_flagged, args
    )
    train_labels = set(
        targets["KDDTrain"]["label"].astype(str).str.strip().str.lower()
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    train_cluster_ids = np.full(len(train_features), -1, dtype=int)
    train_cluster_ids[train_flagged] = cluster_model.labels_
    train_results = write_training_results(
        OUTPUT_DIR,
        train_features,
        targets["KDDTrain"],
        train_scores,
        train_flagged,
        train_cluster_ids,
    )

    metric_rows: list[dict[str, object]] = []
    for split in ("KDDTest", "KDDTest-21"):
        split_features = features[split]
        scores, flagged, cluster_ids = score_split(
            model,
            clusterer,
            cluster_model,
            split_features,
            split,
            threshold,
        )
        write_scored_split(
            OUTPUT_DIR,
            split,
            split_features,
            targets[split],
            scores,
            flagged,
            cluster_ids,
            threshold,
        )
        metric_rows.append(
            evaluate_predictions(
                split,
                targets[split],
                scores,
                flagged,
                cluster_ids,
                threshold,
                train_labels,
            )
        )

    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(OUTPUT_DIR / "evaluation_metrics.csv", index=False)
    write_cluster_profiles(
        OUTPUT_DIR,
        train_results,
        train_features,
        model_schema,
        train_flagged,
    )

    run_config = {
        "algorithm": "IsolationForest",
        "fit_uses_targets": False,
        "training_split": "KDDTrain",
        "feature_profile": "original numeric + train-vocabulary one-hot; engineered alternatives excluded",
        "feature_count": len(model_schema),
        "n_estimators": args.estimators,
        "contamination": "auto",
        "threshold_policy": "training anomaly-score quantile",
        "alert_rate": args.alert_rate,
        "anomaly_score_direction": "higher means more suspicious",
        "cluster_algorithm": "KMeans on flagged KDDTrain records only",
        "requested_clusters": args.clusters,
        "actual_clusters": actual_clusters,
        "random_seed": args.seed,
        "threshold_anomaly_score": threshold,
        "output_directory": str(OUTPUT_DIR),
    }
    write_run_config(OUTPUT_DIR, run_config)

    print(f"Fitted on {len(train_features):,} unlabeled KDDTrain rows.")
    print(f"Features used: {len(model_schema)} (targets excluded from fitting).")
    print(f"Alert threshold: {threshold:.6f}; training alert rate: {train_flagged.mean():.2%}")
    print(f"Clustered training alerts into {actual_clusters} groups.")
    print(f"Results written to: {OUTPUT_DIR}")
    print("\nHeld-out evaluation (labels used only after scoring):")
    print(metrics.to_string(index=False))
