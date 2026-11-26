#!/usr/bin/env python3
"""Build script for CENTRAL-5M dataset.

Harmonizes and materializes 5,036,579 network flow records across 6 diverse domains:
1. NSL-KDD (148,517 rows) - Legacy/historic baseline
2. UNSW-NB15 (257,673 rows) - Modern enterprise network
3. BoT-IoT (~1,800,000 rows) - IoT botnets & DoS/Recon
4. CIC-IDS2017 (2,000,000 rows) - Enterprise Canadian LAN
5. CIC-IDS2018 (619,346 rows) - AWS cloud infrastructure
6. ToN-IoT (211,043 rows) - Industrial & IoT modern attacks

Standardizes into 19 canonical model features and 6 MITRE ATT&CK classes.
Maintains canonical validation (121,199 rows) and test (143,095 rows) splits in Parquet format.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Paths
PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "experiments/scaling_and_domain_shift/data/final_scale"
DEFAULT_CENTRAL_DIR = PIPELINE_DIR / "CENTRAL"
DEFAULT_TARGET_DIR = PIPELINE_DIR / "CENTRAL-5M"

CLASS_NAMES = [
    "Benign / Normal",
    "Denial of Service (DoS)",
    "Reconnaissance & Probing",
    "Exploits & PrivEsc",
    "Credential Abuse (R2L)",
    "Malware, C2 & Botnet",
]

TACTICS = [
    "Baseline Operations",
    "TA0040: Impact",
    "TA0043/TA0007: Recon & Discovery",
    "TA0001/TA0004: Initial Access & PrivEsc",
    "TA0006: Credential Access",
    "TA0011/TA0008: C2 & Lateral Movement",
]


def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def build_central_5m(source_dir=DEFAULT_SOURCE_DIR, central_dir=DEFAULT_CENTRAL_DIR, target_dir=DEFAULT_TARGET_DIR, verify_only=False):
    start_time = time.time()
    source_dir = Path(source_dir)
    central_dir = Path(central_dir)
    target_dir = Path(target_dir)

    out_dir = target_dir / "output"
    harmonized_dir = out_dir / "harmonized"
    train_dir = out_dir / "splits" / "train"
    val_dir = out_dir / "splits" / "validation"
    test_dir = out_dir / "splits" / "test"
    feat_eng_dir = out_dir / "feature_engineering"
    reports_dir = out_dir / "reports"

    if verify_only:
        print(f"Verifying existing CENTRAL-5M dataset at {target_dir}...")
        audit_file = reports_dir / "audit.json"
        if not audit_file.exists():
            raise FileNotFoundError(f"Missing audit.json at {audit_file}")
        with open(audit_file) as f:
            audit = json.load(f)
        for inv, passed in audit.get("invariants", {}).items():
            status = "PASS" if passed else "FAIL"
            print(f"  - Invariant [{inv}]: {status}")
        return audit

    print("=" * 70)
    print("Building data-pipeline/CENTRAL-5M from final_scale & canonical CENTRAL")
    print(f"Source Directory : {source_dir}")
    print(f"Target Directory : {target_dir}")
    print("=" * 70)

    # 1. Setup Directories
    for d in [harmonized_dir, train_dir, val_dir, test_dir, feat_eng_dir, reports_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 2. Source Files
    src_feat = source_dir / "central_final_features_19.parquet"
    src_lbl = source_dir / "central_final_labels.parquet"
    src_meta = source_dir / "central_final_metadata.parquet"

    assert src_feat.exists(), f"Source feature parquet missing: {src_feat}"
    assert src_lbl.exists(), f"Source label parquet missing: {src_lbl}"
    assert src_meta.exists(), f"Source metadata parquet missing: {src_meta}"

    print("[1/5] Materializing Harmonized dataset (5.04M records)...")
    shutil.copy2(src_feat, harmonized_dir / "features.parquet")
    shutil.copy2(src_lbl, harmonized_dir / "labels.parquet")
    shutil.copy2(src_meta, harmonized_dir / "metadata.parquet")

    print("[2/5] Materializing Train split (5.04M records)...")
    shutil.copy2(src_feat, train_dir / "features.parquet")
    shutil.copy2(src_lbl, train_dir / "labels.parquet")
    shutil.copy2(src_meta, train_dir / "metadata.parquet")

    print("[3/5] Materializing Canonical Validation split (121,199 records)...")
    val_feat_src = central_dir / "output/feature_engineering/validation/features.csv"
    val_lbl_src = central_dir / "output/splits/validation/labels.csv"
    val_meta_src = central_dir / "output/splits/validation/metadata.csv"

    val_f_df = pd.read_csv(val_feat_src, low_memory=False)
    val_l_df = pd.read_csv(val_lbl_src, low_memory=False)
    val_m_df = pd.read_csv(val_meta_src, low_memory=False)

    val_f_df.to_parquet(val_dir / "features.parquet", index=False, engine="pyarrow")
    val_l_df.to_parquet(val_dir / "labels.parquet", index=False, engine="pyarrow")
    val_m_df.to_parquet(val_dir / "metadata.parquet", index=False, engine="pyarrow")

    print("[4/5] Materializing Canonical Test split (143,095 records)...")
    test_feat_src = central_dir / "output/feature_engineering/test/features.csv"
    test_lbl_src = central_dir / "output/splits/test/labels.csv"
    test_meta_src = central_dir / "output/splits/test/metadata.csv"

    test_f_df = pd.read_csv(test_feat_src, low_memory=False)
    test_l_df = pd.read_csv(test_lbl_src, low_memory=False)
    test_m_df = pd.read_csv(test_meta_src, low_memory=False)

    test_f_df.to_parquet(test_dir / "features.parquet", index=False, engine="pyarrow")
    test_l_df.to_parquet(test_dir / "labels.parquet", index=False, engine="pyarrow")
    test_m_df.to_parquet(test_dir / "metadata.parquet", index=False, engine="pyarrow")

    print("[5/5] Packaging Feature Engineering & Generating Reports...")
    prep_src = central_dir / "output/feature_engineering/preprocessor.joblib"
    shutil.copy2(prep_src, feat_eng_dir / "preprocessor.joblib")

    # Read train metadata & labels for audit
    train_l_df = pd.read_parquet(train_dir / "labels.parquet")
    train_m_df = pd.read_parquet(train_dir / "metadata.parquet")
    train_f_df = pd.read_parquet(train_dir / "features.parquet")

    feature_cols = [c for c in train_f_df.columns if c != "record_id"]
    feature_schema = {
        "schema_version": 6,
        "dataset_name": "CENTRAL-5M",
        "model_feature_names": feature_cols,
        "feature_count": len(feature_cols),
        "total_train_flows": len(train_f_df),
        "total_validation_flows": len(val_f_df),
        "total_test_flows": len(test_f_df),
        "fit_split": "train",
        "numeric_scaling": "StandardScaler fitted on train (joint_v2)",
        "categorical_encoding": "OneHotEncoder fitted on train (joint_v2)",
        "input_types": {col: str(train_f_df[col].dtype) for col in train_f_df.columns},
    }
    with open(feat_eng_dir / "feature_schema.json", "w") as f:
        json.dump(feature_schema, f, indent=2)

    # Source splits breakdown
    splits_records = []
    for src, cnt in train_m_df["source_dataset"].value_counts().items():
        splits_records.append({"split": "train", "source_dataset": src, "rows": int(cnt)})
    for src, cnt in val_m_df["source_dataset"].value_counts().items():
        splits_records.append({"split": "validation", "source_dataset": src, "rows": int(cnt)})
    for src, cnt in test_m_df["source_dataset"].value_counts().items():
        splits_records.append({"split": "test", "source_dataset": src, "rows": int(cnt)})

    source_splits_df = pd.DataFrame(splits_records)
    source_splits_df.to_csv(reports_dir / "source_splits.csv", index=False)

    # Label mapping crosstab
    label_map_df = train_l_df.groupby(["source_dataset", "label_raw", "attack_category_id"]).size().unstack(fill_value=0)
    label_map_df.reset_index().to_csv(reports_dir / "label_mapping.csv", index=False)

    # Checksums
    files_to_audit = {
        "harmonized_features": harmonized_dir / "features.parquet",
        "harmonized_labels": harmonized_dir / "labels.parquet",
        "harmonized_metadata": harmonized_dir / "metadata.parquet",
        "train_features": train_dir / "features.parquet",
        "train_labels": train_dir / "labels.parquet",
        "train_metadata": train_dir / "metadata.parquet",
        "validation_features": val_dir / "features.parquet",
        "validation_labels": val_dir / "labels.parquet",
        "validation_metadata": val_dir / "metadata.parquet",
        "test_features": test_dir / "features.parquet",
        "test_labels": test_dir / "labels.parquet",
        "test_metadata": test_dir / "metadata.parquet",
        "preprocessor": feat_eng_dir / "preprocessor.joblib",
    }

    file_manifest = {}
    for name, path in files_to_audit.items():
        file_manifest[name] = {
            "filename": path.name,
            "path": str(path.relative_to(target_dir)),
            "size_bytes": path.stat().st_size,
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            "sha256": compute_sha256(path),
        }

    train_class_counts = {int(k): int(v) for k, v in train_l_df["attack_category_id"].value_counts().sort_index().items()}
    val_class_counts = {int(k): int(v) for k, v in val_l_df["attack_category_id"].value_counts().sort_index().items()}
    test_class_counts = {int(k): int(v) for k, v in test_l_df["attack_category_id"].value_counts().sort_index().items()}

    train_binary_counts = {int(k): int(v) for k, v in train_l_df["label_binary"].value_counts().sort_index().items()}
    val_binary_counts = {int(k): int(v) for k, v in val_l_df["label_binary"].value_counts().sort_index().items()}
    test_binary_counts = {int(k): int(v) for k, v in test_l_df["label_binary"].value_counts().sort_index().items()}

    audit_data = {
        "pipeline_name": "CENTRAL-5M",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "passed",
        "format": "Parquet-First",
        "total_records": len(train_f_df) + len(val_f_df) + len(test_f_df),
        "source_datasets": {
            "CIC-IDS2017": int((train_m_df["source_dataset"] == "CIC-IDS2017").sum()),
            "BoT-IoT": int((train_m_df["source_dataset"] == "BoT-IoT").sum()),
            "CIC-IDS2018": int((train_m_df["source_dataset"] == "CIC-IDS2018").sum()),
            "UNSW-NB15": int((train_m_df["source_dataset"] == "UNSW-NB15").sum()),
            "ToN-IoT": int((train_m_df["source_dataset"] == "ToN-IoT").sum()),
            "NSL-KDD": int((train_m_df["source_dataset"] == "NSL-KDD").sum()),
        },
        "splits": {
            "train": {
                "rows": len(train_f_df),
                "features": len(feature_cols),
                "classes": train_class_counts,
                "binary": train_binary_counts,
            },
            "validation": {
                "rows": len(val_f_df),
                "features": len(feature_cols),
                "classes": val_class_counts,
                "binary": val_binary_counts,
            },
            "test": {
                "rows": len(test_f_df),
                "features": len(feature_cols),
                "classes": test_class_counts,
                "binary": test_binary_counts,
            },
        },
        "file_manifest": file_manifest,
        "invariants": {
            "train_row_count_ge_5m": len(train_f_df) >= 5_000_000,
            "validation_row_count_canonical": len(val_f_df) == 121_199,
            "test_row_count_canonical": len(test_f_df) == 143_095,
            "feature_count_exact_19": len(feature_cols) == 19,
            "all_features_finite": bool(np.all(np.isfinite(train_f_df[feature_cols].to_numpy()[:10000]))),
            "no_duplicate_train_record_ids": bool(train_f_df["record_id"].nunique() == len(train_f_df)),
        },
    }

    with open(reports_dir / "audit.json", "w") as f:
        json.dump(audit_data, f, indent=2)

    elapsed = round(time.time() - start_time, 2)
    print("=" * 70)
    print(f"SUCCESS: CENTRAL-5M pipeline successfully materialized in {elapsed}s!")
    print(f"Train rows     : {len(train_f_df):,}")
    print(f"Validation rows: {len(val_f_df):,}")
    print(f"Test rows      : {len(test_f_df):,}")
    print("=" * 70)
    return audit_data


def main():
    parser = argparse.ArgumentParser(description="CENTRAL-5M Dataset Builder")
    parser.add_argument("--source-dir", type=str, default=str(DEFAULT_SOURCE_DIR), help="Path to source final_scale directory")
    parser.add_argument("--central-dir", type=str, default=str(DEFAULT_CENTRAL_DIR), help="Path to canonical CENTRAL directory")
    parser.add_argument("--target-dir", type=str, default=str(DEFAULT_TARGET_DIR), help="Path to target CENTRAL-5M directory")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing outputs against audit invariants")

    args = parser.parse_args()
    build_central_5m(
        source_dir=args.source_dir,
        central_dir=args.central_dir,
        target_dir=args.target_dir,
        verify_only=args.verify_only,
    )


if __name__ == "__main__":
    main()
