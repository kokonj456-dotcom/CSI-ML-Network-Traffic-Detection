#!/usr/bin/env python3
"""
6-Class Threat Taxonomy & Resampling Experiment Pipeline:
- Model 1: NSL Native Features (41 features, ~125k rows - 100% NSL)
- Model 2: UNSW Native Features (42 features, ~175k rows - 100% UNSW)
- Model 3: Harmonized UNSW+NSL Core Features (19 features, ~301k rows, Unweighted Standard)
- Model 4: Harmonized UNSW+NSL Core Features + Borderline-SMOTE (~325k rows resampled)
- Model 5: Harmonized UNSW+NSL Core Features + Inverse Class Weighting (~301k rows weighted)
- Model 6: Harmonized UNSW+NSL Core Features + Hybrid (Borderline-SMOTE + Class Weights)

Evaluated on:
- In-Domain Benchmarks (NSL Test 22,544 rows, UNSW Test 82,332 rows)
- Combined Multi-Domain Benchmark (104,876 rows)
"""

import os
import sys
import json
import time
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, precision_recall_fscore_support
from sklearn.preprocessing import OneHotEncoder
from sklearn.utils.class_weight import compute_sample_weight
from imblearn.over_sampling import BorderlineSMOTE

RANDOM_SEED = 42

CLASS_NAMES = [
    "Benign / Normal",
    "Denial of Service (DoS)",
    "Reconnaissance & Probing",
    "Exploits & PrivEsc",
    "Credential Abuse (R2L)",
    "Malware, C2 & Botnet"
]

MITRE_TACTICS = [
    "Benign Baseline",
    "TA0040: Impact",
    "TA0043/TA0007: Recon & Discovery",
    "TA0001/TA0004: Initial Access & PrivEsc",
    "TA0006/TA0001: Credential Access & R2L",
    "TA0011/TA0008: C2 & Lateral Movement"
]

MITRE_TECHNIQUES = [
    "N/A (Legitimate Traffic)",
    "T1498 (Network DoS), T1499 (Endpoint DoS)",
    "T1595 (Active Scanning), T1046 (Network Service Discovery)",
    "T1190 (Exploit Public-Facing App), T1068 (Privilege Escalation)",
    "T1110 (Brute Force), T1078 (Valid Accounts)",
    "T1071 (Application Layer Protocol), T1210 (Remote Services)"
]

CATEGORY_MAPPING = {
    # 0: Benign / Normal
    "normal": 0, "Normal": 0,
    # 1: Denial of Service
    "dos": 1, "DoS": 1,
    # 2: Reconnaissance & Probing
    "probe": 2, "Probe": 2,
    "reconnaissance": 2, "Reconnaissance": 2,
    "analysis": 2, "Analysis": 2,
    # 3: Exploits & Privilege Escalation
    "exploits": 3, "Exploits": 3,
    "shellcode": 3, "Shellcode": 3,
    "u2r": 3, "U2R": 3,
    # 4: Credential Abuse & Remote Access
    "r2l": 4, "R2L": 4,
    # 5: Malware, C2 & Botnet
    "generic": 5, "Generic": 5,
    "fuzzers": 5, "Fuzzers": 5,
    "backdoor": 5, "Backdoor": 5,
    "worms": 5, "Worms": 5
}

def extract_core_features(df, fitted_encoders=None):
    """
    Transforms raw flow features into 19 joint_v1 standard features.
    """
    dur = df["duration"].fillna(0).values.astype(float)
    bfwd = df["bytes_forward"].fillna(0).values.astype(float)
    bbwd = df["bytes_backward"].fillna(0).values.astype(float)

    log_dur = np.log1p(np.maximum(dur, 0))
    log_bfwd = np.log1p(np.maximum(bfwd, 0))
    log_bbwd = np.log1p(np.maximum(bbwd, 0))
    signed_ratio = log_bfwd - log_bbwd

    num_arr = np.column_stack([log_dur, log_bfwd, log_bbwd, signed_ratio])
    num_cols = ["log_duration", "log_bytes_forward", "log_bytes_backward", "signed_log_bytes_ratio"]

    proto_cats = ["tcp", "udp", "icmp", "other"]
    service_cats = ["dns", "ftp", "http", "https_ssl", "smtp", "ssh", "other"]
    state_cats = ["established", "no-reply", "reset", "other"]

    proto_s = df["protocol"].astype(str).str.lower().apply(lambda x: x if x in proto_cats else "other")
    serv_s = df["service_group"].astype(str).str.lower().apply(lambda x: x if x in service_cats else "other")
    state_s = df["conn_state_group"].astype(str).str.lower().apply(lambda x: x if x in state_cats else "other")

    cat_df = pd.DataFrame({
        "protocol": proto_s,
        "service_group": serv_s,
        "conn_state_group": state_s
    })

    if fitted_encoders is None:
        enc = OneHotEncoder(categories=[proto_cats, service_cats, state_cats], sparse_output=False, handle_unknown="ignore")
        cat_arr = enc.fit_transform(cat_df)
        cat_cols = [f"proto_{c}" for c in proto_cats] + [f"service_{c}" for c in service_cats] + [f"state_{c}" for c in state_cats]
        fitted_encoders = (enc, cat_cols)
    else:
        enc, cat_cols = fitted_encoders
        cat_arr = enc.transform(cat_df)

    all_features = np.hstack([num_arr, cat_arr])
    feature_names = num_cols + cat_cols

    return all_features, feature_names, fitted_encoders

def evaluate_predictions(y_true, y_pred, num_classes=6):
    acc = float(accuracy_score(y_true, y_pred))
    p, r, f1, sup = precision_recall_fscore_support(
        y_true, y_pred, labels=list(range(num_classes)), zero_division=0
    )

    macro_p = float(np.mean(p))
    macro_r = float(np.mean(r))
    macro_f1 = float(np.mean(f1))

    cm = confusion_matrix(y_true, y_pred, labels=list(range(num_classes)))
    row_sums = np.maximum(cm.sum(axis=1, keepdims=True), 1.0)
    cm_norm = (cm.astype(float) / row_sums).round(4)

    # Benign False Positive Rate: false alarms / total actual benign
    benign_fp = int(cm[0, :].sum() - cm[0, 0])
    benign_total = int(cm[0, :].sum())
    benign_fpr = round(float(benign_fp / max(benign_total, 1)), 4)

    per_class = []
    for i in range(num_classes):
        per_class.append({
            "class_id": i,
            "class_name": CLASS_NAMES[i],
            "mitre_tactic": MITRE_TACTICS[i],
            "mitre_technique": MITRE_TECHNIQUES[i],
            "precision": round(float(p[i]), 4),
            "recall": round(float(r[i]), 4),
            "f1_score": round(float(f1[i]), 4),
            "support": int(sup[i])
        })

    return {
        "accuracy": round(acc, 4),
        "macro_precision": round(macro_p, 4),
        "macro_recall": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "benign_fpr": benign_fpr,
        "confusion_matrix_raw": cm.tolist(),
        "confusion_matrix_norm": cm_norm.tolist(),
        "per_class": per_class
    }

def main():
    print("=" * 80)
    print("6-CLASS THREAT TAXONOMY & RESAMPLING EXPERIMENT PIPELINE")
    print("Alignment: MITRE ATT&CK Enterprise Matrix")
    print("=" * 80)

    os.makedirs("6-Class/data", exist_ok=True)
    os.makedirs("6-Class/models", exist_ok=True)

    # ---------------------------------------------------------
    # 1. LOAD HARMONIZED DATA (UNSW + NSL) FOR MODELS 3 - 6
    # ---------------------------------------------------------
    print("\n[Step 1/7] Loading harmonized multi-dataset tables...")
    meta_df = pd.read_csv("data-pipeline/common/output/harmonized/metadata.csv", low_memory=False)
    labels_df = pd.read_csv("data-pipeline/common/output/harmonized/labels.csv", low_memory=False)
    feat_df = pd.read_csv("data-pipeline/common/output/harmonized/features.csv", low_memory=False)

    mask = meta_df["source_dataset"].isin(["UNSW-NB15", "NSL-KDD"])
    meta_sub = meta_df[mask].copy().reset_index(drop=True)
    labels_sub = labels_df[mask].copy().reset_index(drop=True)
    feat_sub = feat_df[mask].copy().reset_index(drop=True)

    meta_sub["target_class"] = labels_sub["label_source_category"].map(CATEGORY_MAPPING)
    if meta_sub["target_class"].isna().sum() > 0:
        raise ValueError(f"Unmapped categories found: {meta_sub[meta_sub['target_class'].isna()]['label_source_category'].unique()}")
    meta_sub["target_class"] = meta_sub["target_class"].astype(int)

    for col in ["duration", "bytes_forward", "bytes_backward", "protocol", "service_group", "conn_state_group"]:
        meta_sub[col] = feat_sub[col]

    print(f"Total harmonized records: {len(meta_sub):,}")
    print("Class distribution in harmonized pool:")
    for cid in range(6):
        count = int((meta_sub["target_class"] == cid).sum())
        print(f"  Class {cid} ({CLASS_NAMES[cid]}): {count:,} records")

    # Split train vs test
    train_pool = meta_sub[meta_sub["data_split"] != "test"].copy().reset_index(drop=True)
    test_nsl = meta_sub[(meta_sub["source_dataset"] == "NSL-KDD") & (meta_sub["data_split"] == "test")].copy().reset_index(drop=True)
    test_unsw = meta_sub[(meta_sub["source_dataset"] == "UNSW-NB15") & (meta_sub["data_split"] == "test")].copy().reset_index(drop=True)
    test_comb = meta_sub[meta_sub["data_split"] == "test"].copy().reset_index(drop=True)

    print(f"\nTrain pool: {len(train_pool):,} rows (NSL {(train_pool['source_dataset'] == 'NSL-KDD').sum():,} + UNSW {(train_pool['source_dataset'] == 'UNSW-NB15').sum():,})")
    print(f"Test sets: NSL={len(test_nsl):,} | UNSW={len(test_unsw):,} | Combined={len(test_comb):,}")

    # Extract 19 Core Features
    print("\nEncoding 19 harmonized core features...")
    X_train_core, core_feat_names, core_encoders = extract_core_features(train_pool)
    y_train_core = train_pool["target_class"].values

    X_test_nsl_core, _, _ = extract_core_features(test_nsl, fitted_encoders=core_encoders)
    y_test_nsl = test_nsl["target_class"].values

    X_test_unsw_core, _, _ = extract_core_features(test_unsw, fitted_encoders=core_encoders)
    y_test_unsw = test_unsw["target_class"].values

    X_test_comb_core, _, _ = extract_core_features(test_comb, fitted_encoders=core_encoders)
    y_test_comb = test_comb["target_class"].values

    # Base XGBoost parameters
    xgb_base_params = {
        "objective": "multi:softprob",
        "num_class": 6,
        "tree_method": "hist",
        "n_estimators": 100,
        "max_depth": 6,
        "learning_rate": 0.1,
        "random_state": RANDOM_SEED,
        "n_jobs": -1
    }

    benchmarks_output = {
        "metadata": {
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_harmonized_records": len(meta_sub),
            "train_pool_size": len(train_pool),
            "test_nsl_size": len(test_nsl),
            "test_unsw_size": len(test_unsw),
            "test_combined_size": len(test_comb),
            "class_names": CLASS_NAMES,
            "mitre_tactics": MITRE_TACTICS,
            "mitre_techniques": MITRE_TECHNIQUES,
            "core_features_count": len(core_feat_names),
            "core_feature_names": core_feat_names
        },
        "models": {}
    }

    # ---------------------------------------------------------
    # 2. MODEL 1: NSL NATIVE FEATURES (41 Features)
    # ---------------------------------------------------------
    print("\n" + "="*50)
    print("[Step 2/7] Training Model 1: NSL Native Features...")
    print("="*50)
    nsl_train_raw = pd.read_csv("data-pipeline/sub-dataset/NSL-KDD/output/cleansing/KDDTrain_clean.csv")
    nsl_test_raw = pd.read_csv("data-pipeline/sub-dataset/NSL-KDD/output/cleansing/KDDTest_clean.csv")

    nsl_train_y = nsl_train_raw["attack_family"].map(CATEGORY_MAPPING).fillna(0).astype(int).values
    nsl_test_y = nsl_test_raw["attack_family"].map(CATEGORY_MAPPING).fillna(0).astype(int).values

    nsl_cat_cols = ["protocol_type", "service", "flag"]
    nsl_num_cols = [c for c in nsl_train_raw.columns if c not in nsl_cat_cols + ["label", "attack_family", "is_attack"]]

    nsl_enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    nsl_X_tr_cat = nsl_enc.fit_transform(nsl_train_raw[nsl_cat_cols])
    nsl_X_te_cat = nsl_enc.transform(nsl_test_raw[nsl_cat_cols])
    nsl_cat_names = list(nsl_enc.get_feature_names_out(nsl_cat_cols))

    nsl_X_tr = np.hstack([nsl_train_raw[nsl_num_cols].fillna(0).values, nsl_X_tr_cat])
    nsl_X_te = np.hstack([nsl_test_raw[nsl_num_cols].fillna(0).values, nsl_X_te_cat])
    nsl_feat_names = nsl_num_cols + nsl_cat_names

    print(f"Model 1 X_train shape: {nsl_X_tr.shape}, X_test shape: {nsl_X_te.shape}")
    m1_params = dict(xgb_base_params)
    m1_params["num_class"] = 5  # NSL only has classes 0, 1, 2, 3, 4 (lacks class 5 Malware/C2)
    m1 = xgb.XGBClassifier(**m1_params)
    t0 = time.time()
    m1.fit(nsl_X_tr, nsl_train_y)
    m1_train_time = round(time.time() - t0, 2)
    m1.save_model("6-Class/models/model1_nsl_native.json")

    m1_preds_nsl = m1.predict(nsl_X_te)
    m1_eval_nsl = evaluate_predictions(nsl_test_y, m1_preds_nsl, num_classes=6)
    print(f"Model 1 In-Domain (NSL Test) Accuracy: {m1_eval_nsl['accuracy']*100:.2f}% | Macro F1: {m1_eval_nsl['macro_f1']*100:.2f}% (Trained in {m1_train_time}s)")

    benchmarks_output["models"]["model1"] = {
        "id": "model1",
        "name": "Model 1: NSL Native Full Features",
        "description": "Trained only on NSL-KDD with all 41 native domain features (121 encoded). Siloed domain baseline.",
        "dataset_scope": "NSL-KDD Alone",
        "feature_type": "Native Domain Features (121)",
        "train_rows": len(nsl_train_raw),
        "train_time_sec": m1_train_time,
        "is_cross_evaluable": False,
        "eval_in_domain": m1_eval_nsl,
        "eval_nsl": m1_eval_nsl,
        "eval_unsw": None,
        "eval_combined": None
    }

    # ---------------------------------------------------------
    # 3. MODEL 2: UNSW NATIVE FEATURES (42 Features)
    # ---------------------------------------------------------
    print("\n" + "="*50)
    print("[Step 3/7] Training Model 2: UNSW Native Features...")
    print("="*50)
    unsw_train_raw = pd.read_csv("data-pipeline/sub-dataset/UNSW-NB15/output/cleansing/UNSW_NB15_training-set.csv")
    unsw_test_raw = pd.read_csv("data-pipeline/sub-dataset/UNSW-NB15/output/cleansing/UNSW_NB15_testing-set.csv")

    unsw_train_y = unsw_train_raw["attack_cat"].map(CATEGORY_MAPPING).fillna(0).astype(int).values
    unsw_test_y = unsw_test_raw["attack_cat"].map(CATEGORY_MAPPING).fillna(0).astype(int).values

    # UNSW has classes [0, 1, 2, 3, 5] (lacks class 4 R2L)
    unsw_internal_map = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4}
    unsw_reverse_map = {0: 0, 1: 1, 2: 2, 3: 3, 4: 5}
    unsw_train_y_internal = np.vectorize(unsw_internal_map.get)(unsw_train_y)

    unsw_exclude = ["orig_row_id", "_duplicate_flag", "id", "attack_cat", "label"]
    unsw_candidate = [c for c in unsw_train_raw.columns if c not in unsw_exclude]
    unsw_cat_cols = ["proto", "service", "state"]
    unsw_num_cols = [c for c in unsw_candidate if c not in unsw_cat_cols]

    unsw_enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    unsw_X_tr_cat = unsw_enc.fit_transform(unsw_train_raw[unsw_cat_cols].astype(str))
    unsw_X_te_cat = unsw_enc.transform(unsw_test_raw[unsw_cat_cols].astype(str))
    unsw_cat_names = list(unsw_enc.get_feature_names_out(unsw_cat_cols))

    unsw_X_tr = np.hstack([unsw_train_raw[unsw_num_cols].fillna(0).values, unsw_X_tr_cat])
    unsw_X_te = np.hstack([unsw_test_raw[unsw_num_cols].fillna(0).values, unsw_X_te_cat])
    unsw_feat_names = unsw_num_cols + unsw_cat_names

    print(f"Model 2 X_train shape: {unsw_X_tr.shape}, X_test shape: {unsw_X_te.shape}")
    m2_params = dict(xgb_base_params)
    m2_params["num_class"] = 5  # Internal 5 classes [0, 1, 2, 3, 4] representing [0, 1, 2, 3, 5]
    m2 = xgb.XGBClassifier(**m2_params)
    t0 = time.time()
    m2.fit(unsw_X_tr, unsw_train_y_internal)
    m2_train_time = round(time.time() - t0, 2)
    m2.save_model("6-Class/models/model2_unsw_native.json")

    m2_preds_internal = m2.predict(unsw_X_te)
    m2_preds_unsw = np.vectorize(unsw_reverse_map.get)(m2_preds_internal)
    m2_eval_unsw = evaluate_predictions(unsw_test_y, m2_preds_unsw, num_classes=6)
    print(f"Model 2 In-Domain (UNSW Test) Accuracy: {m2_eval_unsw['accuracy']*100:.2f}% | Macro F1: {m2_eval_unsw['macro_f1']*100:.2f}% (Trained in {m2_train_time}s)")

    benchmarks_output["models"]["model2"] = {
        "id": "model2",
        "name": "Model 2: UNSW Native Full Features",
        "description": "Trained only on UNSW-NB15 with all 42 native domain features (194 encoded). Siloed domain baseline.",
        "dataset_scope": "UNSW-NB15 Alone",
        "feature_type": "Native Domain Features (194)",
        "train_rows": len(unsw_train_raw),
        "train_time_sec": m2_train_time,
        "is_cross_evaluable": False,
        "eval_in_domain": m2_eval_unsw,
        "eval_nsl": None,
        "eval_unsw": m2_eval_unsw,
        "eval_combined": None
    }

    # ---------------------------------------------------------
    # 4. MODEL 3: HARMONIZED (UNSW + NSL) STANDARD UNWEIGHTED
    # ---------------------------------------------------------
    print("\n" + "="*50)
    print("[Step 4/7] Training Model 3: Harmonized UNSW+NSL Standard...")
    print("="*50)
    m3 = xgb.XGBClassifier(**xgb_base_params)
    t0 = time.time()
    m3.fit(X_train_core, y_train_core)
    m3_train_time = round(time.time() - t0, 2)
    m3.save_model("6-Class/models/model3_harmonized_std.json")

    m3_eval_nsl = evaluate_predictions(y_test_nsl, m3.predict(X_test_nsl_core))
    m3_eval_unsw = evaluate_predictions(y_test_unsw, m3.predict(X_test_unsw_core))
    m3_eval_comb = evaluate_predictions(y_test_comb, m3.predict(X_test_comb_core))

    print(f"Model 3 Combined Test: Acc={m3_eval_comb['accuracy']*100:.2f}% | Macro F1={m3_eval_comb['macro_f1']*100:.2f}% | R2L Recall={m3_eval_comb['per_class'][4]['recall']*100:.2f}% (Trained in {m3_train_time}s)")

    benchmarks_output["models"]["model3"] = {
        "id": "model3",
        "name": "Model 3: Harmonized Standard (Unweighted)",
        "description": "Trained on all UNSW+NSL flows with 19 core features. No oversampling or class weighting applied.",
        "dataset_scope": "Harmonized UNSW+NSL",
        "feature_type": "19 Selected Core Features",
        "train_rows": len(X_train_core),
        "train_time_sec": m3_train_time,
        "is_cross_evaluable": True,
        "eval_in_domain": m3_eval_comb,
        "eval_nsl": m3_eval_nsl,
        "eval_unsw": m3_eval_unsw,
        "eval_combined": m3_eval_comb
    }

    # ---------------------------------------------------------
    # 5. MODEL 4: HARMONIZED (UNSW + NSL) + BORDERLINE-SMOTE
    # ---------------------------------------------------------
    print("\n" + "="*50)
    print("[Step 5/7] Training Model 4: Harmonized UNSW+NSL + Borderline-SMOTE...")
    print("="*50)
    print("Applying Borderline-SMOTE to synthesize boundary samples for Class 4 (R2L: 995 -> 25,000)...")
    # Borderline-SMOTE target: boost Class 4 (R2L) to 25,000 samples
    bsmote = BorderlineSMOTE(
        sampling_strategy={4: 25000},
        random_state=RANDOM_SEED,
        k_neighbors=5,
        m_neighbors=10
    )
    t_smote = time.time()
    X_train_m4, y_train_m4 = bsmote.fit_resample(X_train_core, y_train_core)
    smote_time = round(time.time() - t_smote, 2)
    print(f"Borderline-SMOTE completed in {smote_time}s: train rows expanded from {len(X_train_core):,} to {len(X_train_m4):,}")

    m4 = xgb.XGBClassifier(**xgb_base_params)
    t0 = time.time()
    m4.fit(X_train_m4, y_train_m4)
    m4_train_time = round(time.time() - t0, 2)
    m4.save_model("6-Class/models/model4_borderline_smote.json")

    m4_eval_nsl = evaluate_predictions(y_test_nsl, m4.predict(X_test_nsl_core))
    m4_eval_unsw = evaluate_predictions(y_test_unsw, m4.predict(X_test_unsw_core))
    m4_eval_comb = evaluate_predictions(y_test_comb, m4.predict(X_test_comb_core))

    print(f"Model 4 Combined Test: Acc={m4_eval_comb['accuracy']*100:.2f}% | Macro F1={m4_eval_comb['macro_f1']*100:.2f}% | R2L Recall={m4_eval_comb['per_class'][4]['recall']*100:.2f}% (Trained in {m4_train_time}s)")

    benchmarks_output["models"]["model4"] = {
        "id": "model4",
        "name": "Model 4: Harmonized + Borderline-SMOTE",
        "description": "Trained on UNSW+NSL with Borderline-SMOTE synthesizing boundary flows for minority attacks (R2L 995 -> 25,000).",
        "dataset_scope": "Harmonized UNSW+NSL",
        "feature_type": "19 Selected Core Features",
        "train_rows": len(X_train_m4),
        "train_time_sec": m4_train_time,
        "smote_time_sec": smote_time,
        "is_cross_evaluable": True,
        "eval_in_domain": m4_eval_comb,
        "eval_nsl": m4_eval_nsl,
        "eval_unsw": m4_eval_unsw,
        "eval_combined": m4_eval_comb
    }

    # ---------------------------------------------------------
    # 6. MODEL 5: HARMONIZED (UNSW + NSL) + CLASS WEIGHTING
    # ---------------------------------------------------------
    print("\n" + "="*50)
    print("[Step 6/7] Training Model 5: Harmonized UNSW+NSL + Inverse Class Weighting...")
    print("="*50)
    weights_m5 = compute_sample_weight("balanced", y_train_core)
    print(f"Calculated sample weights. Class 4 weight = {weights_m5[y_train_core == 4][0]:.2f}x vs Class 0 weight = {weights_m5[y_train_core == 0][0]:.2f}x")

    m5 = xgb.XGBClassifier(**xgb_base_params)
    t0 = time.time()
    m5.fit(X_train_core, y_train_core, sample_weight=weights_m5)
    m5_train_time = round(time.time() - t0, 2)
    m5.save_model("6-Class/models/model5_class_weighted.json")

    m5_eval_nsl = evaluate_predictions(y_test_nsl, m5.predict(X_test_nsl_core))
    m5_eval_unsw = evaluate_predictions(y_test_unsw, m5.predict(X_test_unsw_core))
    m5_eval_comb = evaluate_predictions(y_test_comb, m5.predict(X_test_comb_core))

    print(f"Model 5 Combined Test: Acc={m5_eval_comb['accuracy']*100:.2f}% | Macro F1={m5_eval_comb['macro_f1']*100:.2f}% | R2L Recall={m5_eval_comb['per_class'][4]['recall']*100:.2f}% (Trained in {m5_train_time}s)")

    benchmarks_output["models"]["model5"] = {
        "id": "model5",
        "name": "Model 5: Harmonized + Class-Weighted",
        "description": "Trained on UNSW+NSL with inverse class frequencies applied to penalize minority misclassifications heavily.",
        "dataset_scope": "Harmonized UNSW+NSL",
        "feature_type": "19 Selected Core Features",
        "train_rows": len(X_train_core),
        "train_time_sec": m5_train_time,
        "is_cross_evaluable": True,
        "eval_in_domain": m5_eval_comb,
        "eval_nsl": m5_eval_nsl,
        "eval_unsw": m5_eval_unsw,
        "eval_combined": m5_eval_comb
    }

    # ---------------------------------------------------------
    # 7. MODEL 6: HYBRID (BORDERLINE-SMOTE + CLASS WEIGHTING)
    # ---------------------------------------------------------
    print("\n" + "="*50)
    print("[Step 7/7] Training Model 6: Hybrid (Borderline-SMOTE + Class Weights)...")
    print("="*50)
    weights_m6 = compute_sample_weight("balanced", y_train_m4)
    print(f"Calculated sample weights on resampled dataset ({len(X_train_m4):,} rows).")

    m6 = xgb.XGBClassifier(**xgb_base_params)
    t0 = time.time()
    m6.fit(X_train_m4, y_train_m4, sample_weight=weights_m6)
    m6_train_time = round(time.time() - t0, 2)
    m6.save_model("6-Class/models/model6_hybrid.json")

    m6_eval_nsl = evaluate_predictions(y_test_nsl, m6.predict(X_test_nsl_core))
    m6_eval_unsw = evaluate_predictions(y_test_unsw, m6.predict(X_test_unsw_core))
    m6_eval_comb = evaluate_predictions(y_test_comb, m6.predict(X_test_comb_core))

    print(f"Model 6 Combined Test: Acc={m6_eval_comb['accuracy']*100:.2f}% | Macro F1={m6_eval_comb['macro_f1']*100:.2f}% | R2L Recall={m6_eval_comb['per_class'][4]['recall']*100:.2f}% (Trained in {m6_train_time}s)")

    benchmarks_output["models"]["model6"] = {
        "id": "model6",
        "name": "Model 6: Hybrid (Borderline-SMOTE + Class Weights)",
        "description": "Synergistic hybrid combining boundary vector synthesis with inverse class loss penalty.",
        "dataset_scope": "Harmonized UNSW+NSL",
        "feature_type": "19 Selected Core Features",
        "train_rows": len(X_train_m4),
        "train_time_sec": m6_train_time,
        "is_cross_evaluable": True,
        "eval_in_domain": m6_eval_comb,
        "eval_nsl": m6_eval_nsl,
        "eval_unsw": m6_eval_unsw,
        "eval_combined": m6_eval_comb
    }

    # ---------------------------------------------------------
    # FEATURE IMPORTANCE EXTRACTION FOR 19 CORE FEATURES (Model 4)
    # ---------------------------------------------------------
    print("\nExtracting feature importance rankings for 19 core features...")
    booster_m4 = m4.get_booster()
    gain_scores = booster_m4.get_score(importance_type="gain")
    weight_scores = booster_m4.get_score(importance_type="weight")

    importance_list = []
    for idx, fname in enumerate(core_feat_names):
        fkey = f"f{idx}"
        gain = float(gain_scores.get(fkey, 0.0))
        weight = int(weight_scores.get(fkey, 0))
        importance_list.append({
            "feature": fname,
            "gain": round(gain, 2),
            "weight": weight
        })
    importance_list.sort(key=lambda x: x["gain"], reverse=True)
    benchmarks_output["feature_importances"] = importance_list

    # ---------------------------------------------------------
    # SAVE BENCHMARKS JSON
    # ---------------------------------------------------------
    json_path = "6-Class/data/benchmarks.json"
    with open(json_path, "w") as f:
        json.dump(benchmarks_output, f, indent=2)
    print(f"\nSaved complete benchmark results to: {json_path}")

    print("\n" + "="*80)
    print("FINAL SUMMARY: 6-CLASS EXPERIMENTAL BENCHMARK COMPARISON (COMBINED TEST SET: 104,876 FLOWS)")
    print("="*80)
    print(f"{'Model':<35} | {'Combined Acc':<12} | {'Macro F1':<10} | {'R2L Recall':<11} | {'Benign FPR':<10}")
    print("-" * 86)
    for mid in ["model3", "model4", "model5", "model6"]:
        m_info = benchmarks_output["models"][mid]
        comb = m_info["eval_combined"]
        r2l_rec = comb["per_class"][4]["recall"] * 100
        fpr = comb["benign_fpr"] * 100
        print(f"{m_info['name']:<35} | {comb['accuracy']*100:<11.2f}% | {comb['macro_f1']*100:<9.2f}% | {r2l_rec:<10.2f}% | {fpr:<9.2f}%")
    print("="*80)

if __name__ == "__main__":
    main()
