"""
XGBoost Experiment for NSL-KDD Network Intrusion Detection
Supports:
  1. Binary Classification (Normal vs Attack)
  2. Multiclass Classification (Attack Families)
  3. Stratified K-Fold Cross-Validation on KDDTrain
  4. Final Evaluation on KDDTest+ and KDDTest-21
  5. Feature Importance and Confusion Matrix exports
  6. Model persistence (.joblib) into backup folders: model/xgboost/backup/xgboost-{iso-time}/
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from xgboost import XGBClassifier

# NSL-KDD 5-class mapping for novel attacks in test sets
ATTACK_FAMILY_MAPPING = {
    # DoS
    "apache2": "dos",
    "mailbomb": "dos",
    "processtable": "dos",
    "udpstorm": "dos",
    # Probe
    "mscan": "probe",
    "saint": "probe",
    # R2L
    "httptunnel": "r2l",
    "named": "r2l",
    "sendmail": "r2l",
    "snmpgetattack": "r2l",
    "snmpguess": "r2l",
    "worm": "r2l",
    "xlock": "r2l",
    "xsnoop": "r2l",
    # U2R
    "ps": "u2r",
    "sqlattack": "u2r",
    "xterm": "u2r",
}


def load_dataset(data_dir: Path):
    """Load feature-engineered datasets and target files."""
    print("Loading datasets from:", data_dir)
    X_train = pd.read_csv(data_dir / "KDDTrain_features.csv")
    y_train_df = pd.read_csv(data_dir / "KDDTrain_targets.csv")

    X_test = pd.read_csv(data_dir / "KDDTest_features.csv")
    y_test_df = pd.read_csv(data_dir / "KDDTest_targets.csv")

    X_test21 = pd.read_csv(data_dir / "KDDTest-21_features.csv")
    y_test21_df = pd.read_csv(data_dir / "KDDTest-21_targets.csv")

    return X_train, y_train_df, X_test, y_test_df, X_test21, y_test21_df


def prepare_targets(y_df: pd.DataFrame, mode: str, label_mapping: dict = None):
    """Prepare targets for binary or multiclass mode."""
    if mode == "binary":
        return y_df["is_attack"].values, ["Normal", "Attack"], None

    # Multiclass mode: map Unknown test labels to standard families
    families = y_df["attack_family"].astype(str).str.strip().str.lower().copy()
    unknown_mask = families == "unknown"
    if unknown_mask.any():
        for idx in y_df[unknown_mask].index:
            lbl = str(y_df.loc[idx, "label"]).strip().lower()
            mapped = ATTACK_FAMILY_MAPPING.get(lbl, "unknown").lower()
            families.loc[idx] = mapped

    if label_mapping is None:
        # Define canonical class order
        classes = ["normal", "dos", "probe", "r2l", "u2r"]
        label_mapping = {cls: idx for idx, cls in enumerate(classes)}

    y_encoded = families.map(label_mapping).fillna(-1).astype(int).values
    class_display_names = ["Normal", "DoS", "Probe", "R2L", "U2R"]
    return y_encoded, class_display_names, label_mapping


def plot_confusion_matrix(cm, classes, title, output_path):
    """Save formatted confusion matrix heatmap."""
    plt.figure(figsize=(7, 6))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=classes,
        yticklabels=classes,
    )
    plt.title(title, fontsize=13, pad=12)
    plt.xlabel("Predicted Label", fontsize=11)
    plt.ylabel("True Label", fontsize=11)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def plot_feature_importance(model, feature_names, top_n, output_path):
    """Save top N feature importances plot."""
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1][:top_n]

    top_features = [feature_names[i] for i in indices]
    top_scores = importances[indices]

    plt.figure(figsize=(10, 6))
    sns.barplot(x=top_scores, y=top_features, hue=top_features, palette="viridis", legend=False)
    plt.title(f"Top {top_n} XGBoost Feature Importances", fontsize=13)
    plt.xlabel("Relative Importance (Gain / Weight)", fontsize=11)
    plt.ylabel("Features", fontsize=11)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def evaluate_predictions(y_true, y_pred, y_prob, mode, classes):
    """Calculate comprehensive evaluation metrics."""
    valid_mask = y_true >= 0
    y_true_valid = y_true[valid_mask]
    y_pred_valid = y_pred[valid_mask]

    metrics = {
        "accuracy": float(accuracy_score(y_true_valid, y_pred_valid)),
        "balanced_accuracy": float(
            balanced_accuracy_score(y_true_valid, y_pred_valid)
        ),
        "macro_f1": float(
            f1_score(y_true_valid, y_pred_valid, average="macro", zero_division=0)
        ),
        "weighted_f1": float(
            f1_score(y_true_valid, y_pred_valid, average="weighted", zero_division=0)
        ),
    }

    if mode == "binary":
        metrics["precision"] = float(
            precision_score(y_true_valid, y_pred_valid, zero_division=0)
        )
        metrics["recall"] = float(
            recall_score(y_true_valid, y_pred_valid, zero_division=0)
        )
        metrics["f1"] = float(
            f1_score(y_true_valid, y_pred_valid, zero_division=0)
        )
        if y_prob is not None:
            try:
                metrics["roc_auc"] = float(
                    roc_auc_score(y_true_valid, y_prob[valid_mask, 1])
                )
            except Exception:
                pass
    else:
        report = classification_report(
            y_true_valid,
            y_pred_valid,
            target_names=[classes[i] for i in sorted(np.unique(y_true_valid))],
            output_dict=True,
            zero_division=0,
        )
        metrics["per_class"] = report

    cm = confusion_matrix(y_true_valid, y_pred_valid)
    return metrics, cm


def train_and_evaluate(args, save_dir: Path = None):
    start_time = time.time()
    
    if save_dir is None:
        iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        save_dir = Path("model/xgboost/backup") / f"xgboost-{iso_str}"
    
    save_dir.mkdir(parents=True, exist_ok=True)

    data_dir = Path(args.data_dir)
    X_train, y_train_df, X_test, y_test_df, X_test21, y_test21_df = load_dataset(
        data_dir
    )

    y_train, classes, label_mapping = prepare_targets(y_train_df, args.mode)
    y_test, _, _ = prepare_targets(y_test_df, args.mode, label_mapping)
    y_test21, _, _ = prepare_targets(y_test21_df, args.mode, label_mapping)

    print(f"\nMode: {args.mode.upper()}")
    print(f"Classes ({len(classes)}): {classes}")
    print(f"Training shape: {X_train.shape}")
    print(f"Test shape: {X_test.shape}")
    print(f"Test-21 shape: {X_test21.shape}")

    # Set up model parameters
    num_class = len(classes) if args.mode == "multiclass" else None
    objective = (
        "multi:softprob" if args.mode == "multiclass" else "binary:logistic"
    )
    eval_metric = "mlogloss" if args.mode == "multiclass" else "logloss"

    xgb_params = {
        "n_estimators": args.n_estimators,
        "max_depth": args.max_depth,
        "learning_rate": args.learning_rate,
        "subsample": args.subsample,
        "colsample_bytree": args.colsample_bytree,
        "random_state": args.random_state,
        "n_jobs": -1,
        "objective": objective,
        "eval_metric": eval_metric,
    }
    if num_class:
        xgb_params["num_class"] = num_class

    # 1. Stratified K-Fold Cross-Validation on KDDTrain
    cv_scores = {"accuracy": [], "balanced_accuracy": [], "macro_f1": []}
    if args.cv_folds > 1:
        print(f"\n--- Running {args.cv_folds}-Fold Cross-Validation on KDDTrain ---")
        skf = StratifiedKFold(
            n_splits=args.cv_folds, shuffle=True, random_state=args.random_state
        )

        for fold, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train), 1):
            X_fold_train, X_fold_val = (
                X_train.iloc[train_idx],
                X_train.iloc[val_idx],
            )
            y_fold_train, y_fold_val = y_train[train_idx], y_train[val_idx]

            fold_model = XGBClassifier(**xgb_params)
            fold_model.fit(X_fold_train, y_fold_train)

            fold_pred = fold_model.predict(X_fold_val)
            acc = accuracy_score(y_fold_val, fold_pred)
            bal_acc = balanced_accuracy_score(y_fold_val, fold_pred)
            f1_m = f1_score(y_fold_val, fold_pred, average="macro", zero_division=0)

            cv_scores["accuracy"].append(acc)
            cv_scores["balanced_accuracy"].append(bal_acc)
            cv_scores["macro_f1"].append(f1_m)
            print(
                f"  Fold {fold}: Accuracy = {acc:.4f}, Balanced Acc = {bal_acc:.4f}, Macro F1 = {f1_m:.4f}"
            )

        print(
            f"Mean CV Accuracy: {np.mean(cv_scores['accuracy']):.4f} +/- {np.std(cv_scores['accuracy']):.4f}"
        )
        print(
            f"Mean CV Macro F1: {np.mean(cv_scores['macro_f1']):.4f} +/- {np.std(cv_scores['macro_f1']):.4f}"
        )

    # 2. Train Full Model on KDDTrain
    print("\n--- Training Full Model on complete KDDTrain ---")
    model = XGBClassifier(**xgb_params)
    model.fit(X_train, y_train)

    # 3. Evaluate on KDDTest+ and KDDTest-21
    print("\n--- Evaluating on KDDTest+ ---")
    test_pred = model.predict(X_test)
    test_prob = model.predict_proba(X_test)
    test_metrics, test_cm = evaluate_predictions(
        y_test, test_pred, test_prob, args.mode, classes
    )
    print("KDDTest+ Metrics:")
    for k, v in test_metrics.items():
        if k != "per_class":
            print(f"  {k}: {v:.4f}")

    print("\n--- Evaluating on KDDTest-21 (Difficult Subset) ---")
    test21_pred = model.predict(X_test21)
    test21_prob = model.predict_proba(X_test21)
    test21_metrics, test21_cm = evaluate_predictions(
        y_test21, test21_pred, test21_prob, args.mode, classes
    )
    print("KDDTest-21 Metrics:")
    for k, v in test21_metrics.items():
        if k != "per_class":
            print(f"  {k}: {v:.4f}")

    # 4. Save Artifacts, Plots, and .joblib Model
    plot_confusion_matrix(
        test_cm,
        classes,
        f"XGBoost Confusion Matrix ({args.mode}) - KDDTest+",
        save_dir / "confusion_matrix_kddtest.png",
    )
    plot_confusion_matrix(
        test21_cm,
        classes,
        f"XGBoost Confusion Matrix ({args.mode}) - KDDTest-21",
        save_dir / "confusion_matrix_kddtest21.png",
    )
    plot_feature_importance(
        model,
        X_train.columns,
        top_n=20,
        output_path=save_dir / "top_20_feature_importances.png",
    )

    # Save Model .joblib
    model_path = save_dir / "xgboost_model.joblib"
    joblib.dump(model, model_path)
    print(f"Saved model checkpoint: {model_path}")

    # Feature Importance dict for UI
    importances = model.feature_importances_
    top_indices = np.argsort(importances)[::-1][:20]
    top_feature_importance_dict = {
        X_train.columns[i]: float(importances[i]) for i in top_indices
    }

    # Threshold curve precomputation for interactive slider (Binary mode)
    threshold_curve = None
    if args.mode == "binary":
        threshold_curve = []
        for th in [round(x, 2) for x in np.linspace(0.01, 0.99, 99)]:
            p = (test_prob[:, 1] >= th).astype(int)
            p21 = (test21_prob[:, 1] >= th).astype(int)
            threshold_curve.append({
                "threshold": th,
                "accuracy": float(accuracy_score(y_test, p)),
                "precision": float(precision_score(y_test, p, zero_division=0)),
                "recall": float(recall_score(y_test, p, zero_division=0)),
                "f1": float(f1_score(y_test, p, zero_division=0)),
                "confusion_matrix": confusion_matrix(y_test, p).tolist(),
                "test21_accuracy": float(accuracy_score(y_test21, p21)),
                "test21_precision": float(precision_score(y_test21, p21, zero_division=0)),
                "test21_recall": float(recall_score(y_test21, p21, zero_division=0)),
                "test21_f1": float(f1_score(y_test21, p21, zero_division=0)),
                "test21_confusion_matrix": confusion_matrix(y_test21, p21).tolist()
            })

    results_summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "classes": classes,
        "hyperparameters": xgb_params,
        "kddtest_metrics": test_metrics,
        "kddtest21_metrics": test21_metrics,
        "cv_metrics": {
            k: {"mean": float(np.mean(v)), "std": float(np.std(v))}
            for k, v in cv_scores.items()
        }
        if args.cv_folds > 1
        else None,
        "top_features": top_feature_importance_dict,
        "confusion_matrix_kddtest": test_cm.tolist(),
        "confusion_matrix_kddtest21": test21_cm.tolist(),
        "threshold_curve": threshold_curve,
        "model_file": "xgboost_model.joblib",
        "elapsed_seconds": round(time.time() - start_time, 2),
    }

    json_path = save_dir / "evaluation_results.json"
    with open(json_path, "w") as f:
        json.dump(results_summary, f, indent=2)

    print(f"\nResults successfully saved to: {save_dir}")
    print(f"Total time elapsed: {results_summary['elapsed_seconds']}s")
    return results_summary, save_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train and evaluate XGBoost on NSL-KDD")
    parser.add_argument(
        "--data_dir",
        type=str,
        default="data-pipeline/output/NSL-KDD/feature_engineered",
        help="Path to feature-engineered CSV files",
    )
    parser.add_argument(
        "--backup_dir",
        type=str,
        default="model/xgboost/backup",
        help="Root directory for backup runs",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["binary", "multiclass", "both"],
        default="both",
        help="Target classification mode",
    )
    parser.add_argument(
        "--cv_folds",
        type=int,
        default=5,
        help="Number of Stratified K-Fold CV folds",
    )
    parser.add_argument(
        "--n_estimators",
        type=int,
        default=150,
        help="Number of boosting rounds",
    )
    parser.add_argument(
        "--max_depth",
        type=int,
        default=6,
        help="Maximum tree depth",
    )
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=0.1,
        help="Boosting learning rate",
    )
    parser.add_argument(
        "--subsample",
        type=float,
        default=0.8,
        help="Subsample ratio of the training instances",
    )
    parser.add_argument(
        "--colsample_bytree",
        type=float,
        default=0.8,
        help="Subsample ratio of columns when constructing each tree",
    )
    parser.add_argument(
        "--random_state",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )

    args = parser.parse_args()

    iso_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    
    if args.mode == "both":
        print("================ Running Binary Mode ================")
        args.mode = "binary"
        bin_dir = Path(args.backup_dir) / f"xgboost-{iso_str}-binary"
        train_and_evaluate(args, bin_dir)
        
        print("\n================ Running Multiclass Mode ================")
        args.mode = "multiclass"
        multi_dir = Path(args.backup_dir) / f"xgboost-{iso_str}-multiclass"
        train_and_evaluate(args, multi_dir)
    else:
        run_dir = Path(args.backup_dir) / f"xgboost-{iso_str}-{args.mode}"
        train_and_evaluate(args, run_dir)
