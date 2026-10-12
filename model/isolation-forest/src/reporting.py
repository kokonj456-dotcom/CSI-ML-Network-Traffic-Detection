"""Write prediction, alert, cluster-profile, and run-configuration artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def write_training_results(
    output_dir: Path,
    features: pd.DataFrame,
    targets: pd.DataFrame,
    scores: np.ndarray,
    flagged: np.ndarray,
    cluster_ids: np.ndarray,
) -> pd.DataFrame:
    results = pd.DataFrame(
        {
            "row_index": np.arange(len(features)),
            "anomaly_score": scores,
            "is_anomaly": flagged,
            "cluster_id": cluster_ids,
        }
    )
    results = pd.concat([results, targets.reset_index(drop=True)], axis=1)
    results.to_csv(output_dir / "KDDTrain_anomaly_results.csv", index=False)
    return results


def write_scored_split(
    output_dir: Path,
    split: str,
    features: pd.DataFrame,
    targets: pd.DataFrame,
    scores: np.ndarray,
    flagged: np.ndarray,
    cluster_ids: np.ndarray,
    threshold: float,
) -> None:
    results = pd.DataFrame(
        {
            "row_index": np.arange(len(features)),
            "anomaly_score": scores,
            "threshold": threshold,
            "is_anomaly": flagged,
            "cluster_id": cluster_ids,
        }
    )
    results = pd.concat([results, targets.reset_index(drop=True)], axis=1)
    results.to_csv(output_dir / f"{split}_anomaly_results.csv", index=False)

    alerts = features.loc[flagged].reset_index(drop=True).copy()
    alerts.insert(0, "row_index", np.flatnonzero(flagged))
    alerts.insert(1, "anomaly_score", scores[flagged])
    alerts.insert(2, "cluster_id", cluster_ids[flagged])
    alerts = pd.concat([alerts, targets.loc[flagged].reset_index(drop=True)], axis=1)
    alerts.sort_values("anomaly_score", ascending=False).to_csv(
        output_dir / f"{split}_alerts.csv", index=False
    )


def write_cluster_profiles(
    output_dir: Path,
    train_results: pd.DataFrame,
    train_features: pd.DataFrame,
    feature_schema: pd.DataFrame,
    train_flagged: np.ndarray,
) -> None:
    service_columns = [
        column
        for column in feature_schema.loc[
            feature_schema["kind"] == "one_hot", "feature"
        ].astype(str)
        if column.startswith("service=")
    ]
    profile_rows: list[dict[str, object]] = []
    for cluster_id, group in train_results.loc[train_flagged].groupby("cluster_id"):
        family_counts = group["attack_family"].value_counts()
        service_counts = (
            train_features.loc[group.index, service_columns].sum()
            if service_columns
            else pd.Series(dtype=float)
        )
        most_common_service = (
            str(service_counts.idxmax()).split("=", maxsplit=1)[1]
            if not service_counts.empty and service_counts.max() > 0
            else None
        )
        profile_rows.append(
            {
                "cluster_id": int(cluster_id),
                "training_alert_rows": len(group),
                "normal_rows": int((group["is_attack"] == 0).sum()),
                "attack_rows": int((group["is_attack"] == 1).sum()),
                "most_common_attack_family_for_review": (
                    str(family_counts.index[0]) if not family_counts.empty else None
                ),
                "most_common_service": most_common_service,
            }
        )

    pd.DataFrame(profile_rows).to_csv(
        output_dir / "training_alert_cluster_profiles.csv", index=False
    )


def write_run_config(output_dir: Path, config: dict[str, object]) -> None:
    with (output_dir / "run_config.json").open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=2, ensure_ascii=False)
