#!/usr/bin/env python3
"""Script 02: Train 8 XGBoost models and evaluate Cross-Dataset Generalization Matrix.

Models:
1. M1: NSL Specialist (40 features, trained on NSL train)
2. M2: UNSW Specialist (43 features, trained on UNSW train)
3. M3: CIC Specialist (11 features, trained on CIC train)
4. M4: BoT Specialist (10 features, trained on BoT train)
5. M5: CENTRAL 19 (19 features, trained on CENTRAL train 467k)
6. M6: CENTRAL-UNCUT Native (80 features, native NaN, trained on UNCUT train 467k)
7. M7: CENTRAL-UNCUT Imputed (80 features, sentinel -1, trained on UNCUT train 467k)
8. M8: CENTRAL-MAX Scale (19 features, trained on Big Data 1.89M)

Evaluation Sets (5):
1. NSL-KDD Test (22,544 rows)
2. UNSW-NB15 Test (82,332 rows)
3. CIC-IDS2017 Test (18,219 rows)
4. BoT-IoT Test (20,000 rows)
5. CENTRAL Full Test (143,095 rows)

Metrics: Accuracy, Macro F1, Binary F1, False Positive Rate (FPR), Precision, Recall, Latency.
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, precision_score, recall_score

# Directories
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
DATA_DIR = EXP_DIR / "data" / "max_scale"
MODELS_DIR = EXP_DIR / "models"
RESULTS_DIR = EXP_DIR / "results"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_ROOT = EXP_DIR.parent.parent
PIPELINE_DIR = PROJECT_ROOT / "data-pipeline"
UNCUT_DIR = PIPELINE_DIR / "CENTRAL-UNCUT" / "output" / "splits"
CENTRAL_DIR = PIPELINE_DIR / "CENTRAL" / "output"


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def prepare_categorical_features(df):
    df_out = df.copy()
    for col in df_out.columns:
        if df_out[col].dtype == "object" or str(df_out[col].dtype) == "string":
            df_out[col] = df_out[col].astype("category")
    return df_out


def compute_metrics(y_true, y_pred, is_binary=True):
    acc = float(accuracy_score(y_true, y_pred))
    f1_macro = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

    if is_binary:
        f1_bin = float(f1_score(y_true, y_pred, pos_label=1, zero_division=0))
        prec = float(precision_score(y_true, y_pred, pos_label=1, zero_division=0))
        rec = float(recall_score(y_true, y_pred, pos_label=1, zero_division=0))
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()
        fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    else:
        f1_bin = f1_macro
        prec = float(precision_score(y_true, y_pred, average="weighted", zero_division=0))
        rec = float(recall_score(y_true, y_pred, average="weighted", zero_division=0))
        # Overall FPR: treat class 0 as benign, all other classes as attack
        bin_true = (np.array(y_true) != 0).astype(int)
        bin_pred = (np.array(y_pred) != 0).astype(int)
        cm = confusion_matrix(bin_true, bin_pred, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()
        fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0

    return {
        "accuracy": round(acc * 100, 2),
        "f1_macro": round(f1_macro * 100, 2),
        "f1_binary": round(f1_bin * 100, 2),
        "precision": round(prec * 100, 2),
        "recall": round(rec * 100, 2),
        "fpr": round(fpr * 100, 2),
    }


def main():
    start_total = time.time()
    log("Starting Benchmark Suite: 8 Models x 5 Test Sets...")

    # Step 1: Load Test Sets
    log("Loading Test Sets from CENTRAL-UNCUT and CENTRAL...")
    test_uncut_f = pd.read_parquet(UNCUT_DIR / "test/features.parquet")
    test_uncut_l = pd.read_parquet(UNCUT_DIR / "test/labels.parquet")
    test_uncut_m = pd.read_parquet(UNCUT_DIR / "test/metadata.parquet")

    test_19_f = pd.read_csv(CENTRAL_DIR / "feature_engineering/test/features.csv", low_memory=False)
    test_19_l = pd.read_csv(CENTRAL_DIR / "splits/test/labels.csv", low_memory=False)

    test_uncut_f = prepare_categorical_features(test_uncut_f.drop(columns=["record_id"]))
    test_19_f = test_19_f.drop(columns=["record_id"])

    # Prepare Imputed Test Set (-1 for numeric, 'missing' for category)
    test_imputed_f = test_uncut_f.copy()
    for col in test_imputed_f.columns:
        if test_imputed_f[col].dtype.name == "category":
            if "missing" not in test_imputed_f[col].cat.categories:
                test_imputed_f[col] = test_imputed_f[col].cat.add_categories(["missing"])
            test_imputed_f[col] = test_imputed_f[col].fillna("missing")
        else:
            test_imputed_f[col] = test_imputed_f[col].fillna(-1.0)

    # Masks for individual test sets
    test_masks = {
        "NSL-KDD": test_uncut_m["source_dataset"] == "NSL-KDD",
        "UNSW-NB15": test_uncut_m["source_dataset"] == "UNSW-NB15",
        "CIC-IDS2017": test_uncut_m["source_dataset"] == "CIC-IDS2017",
        "BoT-IoT": test_uncut_m["source_dataset"] == "BoT-IoT",
        "CENTRAL Full": np.ones(len(test_uncut_m), dtype=bool),
    }

    log("Test set sizes:")
    for k, m in test_masks.items():
        log(f"  {k:15s}: {m.sum():,} flows")

    # Step 2: Load Training Data
    log("Loading Training Data...")
    train_uncut_f = pd.read_parquet(UNCUT_DIR / "train/features.parquet")
    train_uncut_l = pd.read_parquet(UNCUT_DIR / "train/labels.parquet")
    train_uncut_m = pd.read_parquet(UNCUT_DIR / "train/metadata.parquet")
    train_uncut_clean_f = prepare_categorical_features(train_uncut_f.drop(columns=["record_id"]))

    train_19_f = pd.read_csv(CENTRAL_DIR / "feature_engineering/train/features.csv", low_memory=False).drop(columns=["record_id"])
    train_19_l = pd.read_csv(CENTRAL_DIR / "splits/train/labels.csv", low_memory=False)

    train_max_f = pd.read_parquet(DATA_DIR / "central_max_features_19.parquet").drop(columns=["record_id"])
    train_max_l = pd.read_parquet(DATA_DIR / "central_max_labels.parquet")

    # Specialist Feature Subsets
    core_flow = ["duration", "protocol", "bytes_forward", "bytes_backward", "packets_forward", "packets_backward", "mean_packet_size", "service_group", "conn_state_group"]
    nsl_features = [c for c in train_uncut_clean_f.columns if c.startswith("nsl_") or c in ["duration", "protocol", "bytes_forward", "bytes_backward", "service_group", "conn_state_group"]]
    unsw_features = [c for c in train_uncut_clean_f.columns if c.startswith("unsw_") or c in core_flow + ["dest_port", "ttl_forward", "ttl_backward", "tcp_window_forward", "tcp_window_backward", "flow_rate"]]
    cic_features = [c for c in train_uncut_clean_f.columns if c in core_flow + ["dest_port", "cic_flow_state"]]
    bot_features = [c for c in train_uncut_clean_f.columns if c in core_flow + ["bot_pkSeqID"]]

    # Model definitions: (id, name, group, train_X, train_y_bin, train_y_multi, eval_X_type, feature_cols, train_rows)
    models_config = [
        # 1. NSL Specialist
        {
            "id": "M1_NSL_Specialist",
            "name": "XGBoost (NSL Specialist)",
            "group": "Specialist",
            "feature_count": len(nsl_features),
            "feature_cols": nsl_features,
            "train_mask": train_uncut_m["source_dataset"] == "NSL-KDD",
            "data_type": "uncut_sub",
            "eval_data_type": "uncut_sub",
        },
        # 2. UNSW Specialist
        {
            "id": "M2_UNSW_Specialist",
            "name": "XGBoost (UNSW Specialist)",
            "group": "Specialist",
            "feature_count": len(unsw_features),
            "feature_cols": unsw_features,
            "train_mask": train_uncut_m["source_dataset"] == "UNSW-NB15",
            "data_type": "uncut_sub",
            "eval_data_type": "uncut_sub",
        },
        # 3. CIC Specialist
        {
            "id": "M3_CIC_Specialist",
            "name": "XGBoost (CIC Specialist)",
            "group": "Specialist",
            "feature_count": len(cic_features),
            "feature_cols": cic_features,
            "train_mask": train_uncut_m["source_dataset"] == "CIC-IDS2017",
            "data_type": "uncut_sub",
            "eval_data_type": "uncut_sub",
        },
        # 4. BoT Specialist
        {
            "id": "M4_BoT_Specialist",
            "name": "XGBoost (BoT Specialist)",
            "group": "Specialist",
            "feature_count": len(bot_features),
            "feature_cols": bot_features,
            "train_mask": train_uncut_m["source_dataset"] == "BoT-IoT",
            "data_type": "uncut_sub",
            "eval_data_type": "uncut_sub",
        },
        # 5. CENTRAL 19
        {
            "id": "M5_CENTRAL_19",
            "name": "XGBoost (CENTRAL 19)",
            "group": "Harmonized",
            "feature_count": 19,
            "feature_cols": list(train_19_f.columns),
            "data_type": "central_19",
            "eval_data_type": "central_19",
        },
        # 6. CENTRAL-UNCUT Native
        {
            "id": "M6_CENTRAL_UNCUT_Native",
            "name": "XGBoost (UNCUT Native NaN)",
            "group": "Harmonized",
            "feature_count": 80,
            "feature_cols": list(train_uncut_clean_f.columns),
            "data_type": "uncut_full",
            "eval_data_type": "uncut_full",
        },
        # 7. CENTRAL-UNCUT Imputed
        {
            "id": "M7_CENTRAL_UNCUT_Imputed",
            "name": "XGBoost (UNCUT Imputed -1)",
            "group": "Harmonized",
            "feature_count": 80,
            "feature_cols": list(train_uncut_clean_f.columns),
            "data_type": "uncut_imputed",
            "eval_data_type": "uncut_imputed",
        },
        # 8. CENTRAL-MAX Scale
        {
            "id": "M8_CENTRAL_MAX_Scale",
            "name": "XGBoost (CENTRAL-MAX Big Data)",
            "group": "Data Scaling",
            "feature_count": 19,
            "feature_cols": list(train_max_f.columns),
            "data_type": "max_scale",
            "eval_data_type": "central_19",
        },
    ]

    # Prepare Imputed Train Set
    train_imputed_f = train_uncut_clean_f.copy()
    for col in train_imputed_f.columns:
        if train_imputed_f[col].dtype.name == "category":
            if "missing" not in train_imputed_f[col].cat.categories:
                train_imputed_f[col] = train_imputed_f[col].cat.add_categories(["missing"])
            train_imputed_f[col] = train_imputed_f[col].fillna("missing")
        else:
            train_imputed_f[col] = train_imputed_f[col].fillna(-1.0)

    # Master results container
    benchmark_results = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "total_models": len(models_config),
            "test_sets": list(test_masks.keys()),
        },
        "models": {},
        "matrices": {
            "binary": {},
            "multiclass": {},
        },
    }

    # Training and Evaluation Loop
    for cfg in models_config:
        mid = cfg["id"]
        mname = cfg["name"]
        log(f"\n==========================================")
        log(f"Processing Model: {mname} ({mid})")
        log(f"==========================================")

        # Prepare Training X and y
        dt = cfg["data_type"]
        if dt == "uncut_sub":
            mask = cfg["train_mask"]
            X_train = train_uncut_clean_f.loc[mask, cfg["feature_cols"]]
            y_train_bin = train_uncut_l.loc[mask, "label_binary"].to_numpy(dtype=int)
            y_train_multi = train_uncut_l.loc[mask, "attack_category_id"].to_numpy(dtype=int)
        elif dt == "uncut_full":
            X_train = train_uncut_clean_f
            y_train_bin = train_uncut_l["label_binary"].to_numpy(dtype=int)
            y_train_multi = train_uncut_l["attack_category_id"].to_numpy(dtype=int)
        elif dt == "uncut_imputed":
            X_train = train_imputed_f
            y_train_bin = train_uncut_l["label_binary"].to_numpy(dtype=int)
            y_train_multi = train_uncut_l["attack_category_id"].to_numpy(dtype=int)
        elif dt == "central_19":
            X_train = train_19_f
            y_train_bin = train_19_l["label_binary"].to_numpy(dtype=int)
            y_train_multi = train_19_l["attack_category_id"].to_numpy(dtype=int)
        elif dt == "max_scale":
            X_train = train_max_f
            y_train_bin = train_max_l["label_binary"].to_numpy(dtype=int)
            y_train_multi = train_max_l["attack_category_id"].to_numpy(dtype=int)

        train_rows = len(X_train)
        log(f"Training on {train_rows:,} rows with {X_train.shape[1]} features...")

        # 1. Train Binary Classifier
        t0 = time.time()
        clf_bin = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            n_jobs=4,
            random_state=42,
            enable_categorical=True,
            tree_method="hist",
        )
        clf_bin.fit(X_train, y_train_bin)
        train_time_bin = round(time.time() - t0, 2)
        clf_bin.save_model(MODELS_DIR / f"{mid}_binary.json")
        log(f"Binary model trained in {train_time_bin}s.")

        # 2. Train Multiclass Classifier (with local-to-global class mapping for missing classes)
        t0 = time.time()
        present_classes = np.sort(np.unique(y_train_multi))
        local_to_global = dict(enumerate(present_classes))
        global_to_local = {v: k for k, v in local_to_global.items()}
        y_train_mapped = np.array([global_to_local[v] for v in y_train_multi])

        clf_multi = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            n_jobs=4,
            random_state=42,
            enable_categorical=True,
            tree_method="hist",
            num_class=len(present_classes),
            objective="multi:softmax",
        )
        clf_multi.fit(X_train, y_train_mapped)
        train_time_multi = round(time.time() - t0, 2)
        clf_multi.save_model(MODELS_DIR / f"{mid}_multiclass.json")
        log(f"Multiclass model trained in {train_time_multi}s on {len(present_classes)} unique classes.")

        # 3. Evaluate Across All 5 Test Sets
        edt = cfg["eval_data_type"]
        eval_results_bin = {}
        eval_results_multi = {}

        for tname, tmask in test_masks.items():
            # Slice Test Features
            if edt == "uncut_sub":
                X_test = test_uncut_f.loc[tmask, cfg["feature_cols"]]
            elif edt == "uncut_full":
                X_test = test_uncut_f.loc[tmask]
            elif edt == "uncut_imputed":
                X_test = test_imputed_f.loc[tmask]
            elif edt == "central_19":
                X_test = test_19_f.loc[tmask]

            y_true_bin = test_uncut_l.loc[tmask, "label_binary"].to_numpy(dtype=int)
            y_true_multi = test_uncut_l.loc[tmask, "attack_category_id"].to_numpy(dtype=int)

            # Measure Inference Latency
            t_infer = time.time()
            preds_bin = clf_bin.predict(X_test)
            latency_bin_ms = round(((time.time() - t_infer) / len(X_test)) * 1000 * 1000, 3)  # ms per 1000 flows

            preds_local = clf_multi.predict(X_test)
            preds_multi = np.array([local_to_global[p] for p in preds_local])

            m_bin = compute_metrics(y_true_bin, preds_bin, is_binary=True)
            m_bin["latency_ms_per_1k"] = latency_bin_ms
            eval_results_bin[tname] = m_bin

            m_multi = compute_metrics(y_true_multi, preds_multi, is_binary=False)
            eval_results_multi[tname] = m_multi

            log(f"  Eval on {tname:15s} | Binary F1: {m_bin['f1_binary']}% | Multi F1: {m_multi['f1_macro']}% | FPR: {m_bin['fpr']}%")

        # In-Domain Peak vs Average Out-of-Domain
        if "Specialist" in mname:
            in_domain_name = {"M1_NSL_Specialist": "NSL-KDD", "M2_UNSW_Specialist": "UNSW-NB15", "M3_CIC_Specialist": "CIC-IDS2017", "M4_BoT_Specialist": "BoT-IoT"}[mid]
            in_domain_f1 = eval_results_bin[in_domain_name]["f1_binary"]
            ood_names = [k for k in ["NSL-KDD", "UNSW-NB15", "CIC-IDS2017", "BoT-IoT"] if k != in_domain_name]
            avg_ood_f1 = round(float(np.mean([eval_results_bin[k]["f1_binary"] for k in ood_names])), 2)
            gen_gap = round(in_domain_f1 - avg_ood_f1, 2)
        else:
            in_domain_name = "CENTRAL Full"
            in_domain_f1 = eval_results_bin["CENTRAL Full"]["f1_binary"]
            sub_names = ["NSL-KDD", "UNSW-NB15", "CIC-IDS2017", "BoT-IoT"]
            avg_ood_f1 = round(float(np.mean([eval_results_bin[k]["f1_binary"] for k in sub_names])), 2)
            gen_gap = round(in_domain_f1 - avg_ood_f1, 2)

        benchmark_results["models"][mid] = {
            "id": mid,
            "name": mname,
            "group": cfg["group"],
            "features_count": cfg["feature_count"],
            "train_rows": train_rows,
            "train_time_seconds": train_time_bin + train_time_multi,
            "in_domain_name": in_domain_name,
            "in_domain_f1_binary": in_domain_f1,
            "avg_cross_domain_f1_binary": avg_ood_f1,
            "generalization_gap": gen_gap,
            "eval_binary": eval_results_bin,
            "eval_multiclass": eval_results_multi,
        }

        benchmark_results["matrices"]["binary"][mname] = {k: v["f1_binary"] for k, v in eval_results_bin.items()}
        benchmark_results["matrices"]["multiclass"][mname] = {k: v["f1_macro"] for k, v in eval_results_multi.items()}

    # Step 4: Export Summary Results
    log("\nExporting Benchmark Results to JSON...")
    results_path = RESULTS_DIR / "benchmark_results.json"
    with open(results_path, "w", encoding="utf8") as f:
        json.dump(benchmark_results, f, indent=2)

    # Export Matrix CSVs
    pd.DataFrame(benchmark_results["matrices"]["binary"]).T.to_csv(RESULTS_DIR / "cross_dataset_matrix_binary.csv")
    pd.DataFrame(benchmark_results["matrices"]["multiclass"]).T.to_csv(RESULTS_DIR / "cross_dataset_matrix_multiclass.csv")

    log(f"All 8 Models trained & evaluated in {time.time() - start_total:.1f}s.")
    log(f"Results saved to {results_path}")


if __name__ == "__main__":
    main()
