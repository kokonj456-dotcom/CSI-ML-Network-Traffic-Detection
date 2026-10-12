"""Post-hoc benchmark metrics; these labels are never inputs to model fitting."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def safe_auc_metrics(y_true: np.ndarray, scores: np.ndarray) -> tuple[float | None, float | None]:
    if np.unique(y_true).size < 2:
        return None, None
    return float(roc_auc_score(y_true, scores)), float(average_precision_score(y_true, scores))


def evaluate_predictions(
    split: str,
    targets: pd.DataFrame,
    scores: np.ndarray,
    flagged: np.ndarray,
    cluster_ids: np.ndarray,
    threshold: float,
    train_labels: set[str],
) -> dict[str, object]:
    """Calculate ranking and threshold metrics after predictions are finalized."""
    y_true = targets["is_attack"].astype(int).to_numpy()
    roc_auc, average_precision = safe_auc_metrics(y_true, scores)
    matrix = confusion_matrix(y_true, flagged.astype(int), labels=[0, 1])
    tn, fp, fn, tp = (int(value) for value in matrix.ravel())

    attack_labels = targets["label"].astype(str).str.strip().str.lower()
    unseen_attack = (attack_labels != "normal") & (~attack_labels.isin(train_labels))
    unseen_recall = (
        float(flagged[unseen_attack.to_numpy()].mean())
        if unseen_attack.any()
        else None
    )

    return {
        "dataset": split,
        "rows": len(targets),
        "alert_rate": float(flagged.mean()),
        "threshold_anomaly_score": float(threshold),
        "roc_auc": roc_auc,
        "average_precision": average_precision,
        "precision_at_threshold": float(precision_score(y_true, flagged, zero_division=0)),
        "recall_at_threshold": float(recall_score(y_true, flagged, zero_division=0)),
        "f1_at_threshold": float(f1_score(y_true, flagged, zero_division=0)),
        "false_positive_rate": float(fp / (fp + tn)) if (fp + tn) else None,
        "true_negative": tn,
        "false_positive": fp,
        "false_negative": fn,
        "true_positive": tp,
        "flagged_clusters": int(np.unique(cluster_ids[flagged]).size),
        "unseen_attack_rows": int(unseen_attack.sum()),
        "unseen_attack_recall": unseen_recall,
    }
