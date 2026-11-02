#!/usr/bin/env python3
"""
Borderline-SMOTE Minority Oversampling Pipeline for Central Dataset
Applies Borderline-SMOTE to synthesize boundary samples for minority attack classes
(specifically Class 4: Credential Abuse / R2L) within the 19-dimensional harmonized space.

Exports:
- data-pipeline/CENTRAL/output/smote/features.csv
- data-pipeline/CENTRAL/output/smote/features_encoded_19.csv
- data-pipeline/CENTRAL/output/smote/labels.csv
- data-pipeline/CENTRAL/output/smote/metadata.csv
- data-pipeline/CENTRAL/output/smote/smote_report.json
- data-pipeline/CENTRAL/output/splits/train_smote/ (features, labels, metadata)
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.preprocessing import OneHotEncoder
from imblearn.over_sampling import BorderlineSMOTE

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CENTRAL_DIR = PROJECT_ROOT / "data-pipeline" / "CENTRAL"

CLASS_NAMES = [
    "Benign / Normal",
    "Denial of Service (DoS)",
    "Reconnaissance & Probing",
    "Exploits & PrivEsc",
    "Credential Abuse (R2L)",
    "Malware, C2 & Botnet"
]

MITRE_TACTICS = [
    "Baseline Operations",
    "TA0040: Impact",
    "TA0043/TA0007: Recon & Discovery",
    "TA0001/TA0004: Initial Access & PrivEsc",
    "TA0006: Credential Access",
    "TA0011/TA0008: C2 & Lateral Movement"
]

def encode_19_features(df):
    """Transform raw flow attributes into the 19-dimensional joint profile."""
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

    cat_df = pd.DataFrame({"protocol": proto_s, "service_group": serv_s, "conn_state_group": state_s})

    enc = OneHotEncoder(categories=[proto_cats, service_cats, state_cats], sparse_output=False, handle_unknown="ignore")
    cat_arr = enc.fit_transform(cat_df)
    cat_cols = [f"proto_{c}" for c in proto_cats] + [f"service_{c}" for c in service_cats] + [f"state_{c}" for c in state_cats]

    all_features = np.hstack([num_arr, cat_arr])
    feature_names = num_cols + cat_cols
    return all_features, feature_names, (proto_cats, service_cats, state_cats)

def main():
    parser = argparse.ArgumentParser(description="Apply Borderline-SMOTE to Central training split")
    parser.add_argument("--split", type=str, default="train_full", choices=["train", "train_full"], help="Training split to resample")
    parser.add_argument("--target_class", type=int, default=4, help="Target class ID to oversample (default 4: R2L)")
    parser.add_argument("--target_samples", type=int, default=40000, help="Target count for the minority class")
    parser.add_argument("--k_neighbors", type=int, default=5, help="Number of nearest neighbors")
    parser.add_argument("--m_neighbors", type=int, default=10, help="Number of neighbors for danger boundary calculation")
    parser.add_argument("--random_state", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    split_dir = CENTRAL_DIR / "output" / "splits" / args.split
    feat_path = split_dir / "features.csv"
    lbl_path = split_dir / "labels.csv"
    meta_path = split_dir / "metadata.csv"

    if not (feat_path.is_file() and lbl_path.is_file() and meta_path.is_file()):
        print(f"Error: Missing split files in {split_dir}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print("CENTRAL DATASET BORDERLINE-SMOTE PIPELINE")
    print(f"Split: {args.split} | Target Class: {args.target_class} ({CLASS_NAMES[args.target_class]}) | Target Count: {args.target_samples:,}")
    print("=" * 80)

    print(f"\n[1/5] Loading {args.split} split from {split_dir}...")
    t0 = time.time()
    features_orig = pd.read_csv(feat_path, low_memory=False)
    labels_orig = pd.read_csv(lbl_path, low_memory=False)
    metadata_orig = pd.read_csv(meta_path, low_memory=False)
    n_orig = len(features_orig)
    print(f"  Loaded {n_orig:,} rows in {time.time() - t0:.2f}s")

    # Extract 19 features
    print("\n[2/5] Transforming into 19-dimensional joint feature space...")
    X_orig, feat_cols, (proto_cats, serv_cats, state_cats) = encode_19_features(features_orig)
    y_orig = labels_orig["attack_category_id"].values.astype(int)

    class_counts_before = {int(c): int((y_orig == c).sum()) for c in range(6)}
    print("Class distribution before resampling:")
    for c in range(6):
        cnt = class_counts_before[c]
        print(f"  Class {c} ({CLASS_NAMES[c]:<25}): {cnt:>7,} rows ({cnt / n_orig * 100:>5.2f}%)")

    current_target = class_counts_before[args.target_class]
    if current_target >= args.target_samples:
        print(f"Class {args.target_class} already has {current_target:,} samples >= target {args.target_samples:,}. Exiting.")
        return

    # Apply Borderline-SMOTE
    print(f"\n[3/5] Applying Borderline-SMOTE (k={args.k_neighbors}, m={args.m_neighbors})...")
    print(f"  Class {args.target_class} count: {current_target:,} -> Target: {args.target_samples:,} (synthesizing {args.target_samples - current_target:,} boundary samples)")
    t_smote = time.time()
    bsmote = BorderlineSMOTE(
        sampling_strategy={args.target_class: args.target_samples},
        random_state=args.random_state,
        k_neighbors=args.k_neighbors,
        m_neighbors=args.m_neighbors
    )
    X_res, y_res = bsmote.fit_resample(X_orig, y_orig)
    smote_duration = round(time.time() - t_smote, 2)
    n_total = len(X_res)
    n_synth = n_total - n_orig
    print(f"  Borderline-SMOTE complete in {smote_duration}s! Total flows: {n_total:,} (+{n_synth:,} synthetic flows)")

    class_counts_after = {int(c): int((y_res == c).sum()) for c in range(6)}
    print("\nClass distribution after resampling:")
    for c in range(6):
        cnt = class_counts_after[c]
        print(f"  Class {c} ({CLASS_NAMES[c]:<25}): {cnt:>7,} rows ({cnt / n_total * 100:>5.2f}%)")

    # [4/5] Inverting synthetic samples back to tabular representations
    print("\n[4/5] Generating tabular feature representations for synthetic flows...")
    X_synth = X_res[n_orig:]
    y_synth = y_res[n_orig:]

    # Inverse continuous transforms
    synth_dur = np.expm1(X_synth[:, 0])
    synth_bfwd = np.round(np.expm1(X_synth[:, 1])).astype(int)
    synth_bbwd = np.round(np.expm1(X_synth[:, 2])).astype(int)

    # Inverse categorical transforms (argmax over one-hot slices)
    proto_slice = X_synth[:, 4:8]
    serv_slice = X_synth[:, 8:15]
    state_slice = X_synth[:, 15:19]

    synth_proto = [proto_cats[idx] for idx in np.argmax(proto_slice, axis=1)]
    synth_serv = [serv_cats[idx] for idx in np.argmax(serv_slice, axis=1)]
    synth_state = [state_cats[idx] for idx in np.argmax(state_slice, axis=1)]

    synth_ids = [f"SMOTE_C4_{i+1:06d}" for i in range(n_synth)]

    features_synth_df = pd.DataFrame({
        "record_id": synth_ids,
        "duration": synth_dur,
        "protocol": synth_proto,
        "bytes_forward": synth_bfwd,
        "bytes_backward": synth_bbwd,
        "service_group": synth_serv,
        "conn_state_group": synth_state,
        "packets_forward": np.nan,
        "packets_backward": np.nan,
        "mean_packet_size": np.nan,
        "ttl_forward": np.nan,
        "ttl_backward": np.nan,
        "tcp_window_forward": np.nan,
        "tcp_window_backward": np.nan,
        "nsl_hot": np.nan,
        "nsl_logged_in": np.nan,
        "nsl_failed_logins": np.nan,
        "nsl_root_shell": np.nan,
        "nsl_count_2s": np.nan,
        "nsl_srv_count_2s": np.nan,
        "nsl_same_srv_rate_2s": np.nan,
        "nsl_serror_rate_2s": np.nan
    })

    labels_synth_df = pd.DataFrame({
        "record_id": synth_ids,
        "label_raw": "Synthetic_BorderlineSMOTE_R2L",
        "label_source_category": "R2L",
        "attack_category": CLASS_NAMES[args.target_class],
        "attack_category_id": args.target_class,
        "label_binary": 1,
        "mitre_tactic": MITRE_TACTICS[args.target_class]
    })

    metadata_synth_df = pd.DataFrame({
        "record_id": synth_ids,
        "source_dataset": "Synthetic_BorderlineSMOTE",
        "orig_row_id": [f"SMOTE_{i+1:06d}" for i in range(n_synth)],
        "source_split": "train",
        "capture_time": np.nan,
        "split_group": "synthetic_resampled",
        "dedup_flag": False,
        "sample_weight": 1.0,
        "has_duration": True,
        "invalid_duration": False,
        "has_protocol": True,
        "has_directional_bytes": True,
        "invalid_bytes_forward": False,
        "invalid_bytes_backward": False,
        "has_capture_time": False,
        "has_service": True,
        "has_connection_state": True,
        "has_packet_stats": False,
        "has_tcp_details": False,
        "has_nsl_content": False,
        "has_nsl_window": False,
        "is_kddtest21_view": False,
        "data_split": f"{args.split}_smote"
    })

    # Combine original and synthetic
    features_full = pd.concat([features_orig, features_synth_df], ignore_index=True)
    labels_full = pd.concat([labels_orig, labels_synth_df], ignore_index=True)
    metadata_full = pd.concat([metadata_orig, metadata_synth_df], ignore_index=True)

    labels_full["is_synthetic"] = [False] * n_orig + [True] * n_synth
    metadata_full["is_synthetic"] = [False] * n_orig + [True] * n_synth

    # Also build 19-encoded dataframe
    encoded_19_df = pd.DataFrame(X_res, columns=feat_cols)
    encoded_19_df.insert(0, "record_id", labels_full["record_id"])
    encoded_19_df["attack_category_id"] = y_res

    # [5/5] Save outputs
    print("\n[5/5] Saving outputs...")
    out_smote_dir = CENTRAL_DIR / "output" / "smote"
    out_smote_dir.mkdir(parents=True, exist_ok=True)

    features_full.to_csv(out_smote_dir / "features.csv", index=False)
    labels_full.to_csv(out_smote_dir / "labels.csv", index=False)
    metadata_full.to_csv(out_smote_dir / "metadata.csv", index=False)
    encoded_19_df.to_csv(out_smote_dir / "features_encoded_19.csv", index=False)

    # Save to split directory
    out_split_smote = CENTRAL_DIR / "output" / "splits" / f"{args.split}_smote"
    out_split_smote.mkdir(parents=True, exist_ok=True)
    features_full.to_csv(out_split_smote / "features.csv", index=False)
    labels_full.to_csv(out_split_smote / "labels.csv", index=False)
    metadata_full.to_csv(out_split_smote / "metadata.csv", index=False)

    # Generate SMOTE report
    report = {
        "pipeline": "Borderline-SMOTE Central Oversampling",
        "source_split": args.split,
        "target_class_id": args.target_class,
        "target_class_name": CLASS_NAMES[args.target_class],
        "k_neighbors": args.k_neighbors,
        "m_neighbors": args.m_neighbors,
        "random_state": args.random_state,
        "duration_seconds": smote_duration,
        "original_rows": n_orig,
        "synthetic_rows": n_synth,
        "total_rows": n_total,
        "class_distribution_before": class_counts_before,
        "class_distribution_after": class_counts_after
    }
    with open(out_smote_dir / "smote_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"SMOTE outputs exported to: {out_smote_dir}")
    print(f"Split exported to: {out_split_smote}")
    print("\n" + "=" * 80)
    print("BORDERLINE-SMOTE PIPELINE COMPLETE!")
    print("=" * 80)

if __name__ == "__main__":
    main()

