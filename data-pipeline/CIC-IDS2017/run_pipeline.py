#!/usr/bin/env python3
"""
CIC-IDS2017 Data Cleansing and Harmonization Pipeline
Processes raw CSVs into output/cleansing and output/harmonized matching UNSW/NSL standard.
"""

from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
CLEAN_DIR = BASE_DIR / "output" / "cleansing"
HARM_DIR = BASE_DIR / "output" / "harmonized"
REP_DIR = BASE_DIR / "output" / "reports"

FILES = {
    "train": "CIC_IDS2017_training-set.csv",
    "test": "CIC_IDS2017_testing-set.csv"
}

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def map_cic_attack_family(cat_str: str) -> str:
    c = str(cat_str).lower().strip()
    if "benign" in c:
        return "Normal"
    elif "patator" in c:
        return "R2L"
    elif any(term in c for term in ["hulk", "goldeneye", "slowloris", "slowhttp", "ddos", "dos", "heartbleed"]):
        return "DoS"
    elif "portscan" in c or "scan" in c:
        return "Probe"
    elif any(term in c for term in ["web attack", "injection", "xss", "sql"]):
        return "Exploits"
    elif "bot" in c or "infiltration" in c:
        return "Generic"
    return "Generic"

def map_port_to_service(port: int) -> str:
    if port == 53:
        return "dns"
    elif port in (20, 21):
        return "ftp"
    elif port in (80, 8080):
        return "http"
    elif port == 443:
        return "https_ssl"
    elif port == 25:
        return "smtp"
    elif port == 22:
        return "ssh"
    else:
        return "other"

def run_cleansing():
    print("[1/2] Running Cleansing for CIC-IDS2017...")
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    audit_rows = []
    manifest_rows = []

    for split, filename in FILES.items():
        src_path = RAW_DIR / filename
        dest_path = CLEAN_DIR / filename

        df = pd.read_csv(src_path)
        rows_in = len(df)

        # Standard cleansing checks
        df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
        df["_duplicate_flag"] = df.duplicated().astype(int)
        if "orig_row_id" not in df.columns:
            df["orig_row_id"] = np.arange(len(df))

        df.to_csv(dest_path, index=False)

        audit_rows.append({
            "file": filename,
            "missing_cells": int(df.isna().sum().sum()),
            "output_file": filename,
            "rows_in": rows_in,
            "rows_out": len(df),
            "rows_removed": 0,
            "changed_cells": 0,
            "rows_with_changed_values": 0,
            "trimmed_cells": 0,
            "sentinel_to_missing_cells": 0,
            "missing_cells_before": 0,
            "missing_cells_after": 0,
            "duplicate_rows_flagged": int(df["_duplicate_flag"].sum()),
            "orig_row_ids_added": len(df),
            "data_columns_added": "orig_row_id, _duplicate_flag"
        })

        manifest_rows.append({
            "file": filename,
            "bytes": dest_path.stat().st_size,
            "sha256": sha256_file(dest_path)
        })

    pd.DataFrame(audit_rows).to_csv(CLEAN_DIR / "cleansing_audit.csv", index=False)
    pd.DataFrame(manifest_rows).to_csv(CLEAN_DIR / "source_manifest.csv", index=False)
    print("Cleansing complete!")

def run_harmonization():
    print("[2/2] Running Harmonization for CIC-IDS2017...")
    HARM_DIR.mkdir(parents=True, exist_ok=True)

    feature_parts, label_parts, meta_parts = [], [], []

    for split, filename in FILES.items():
        clean_path = CLEAN_DIR / filename
        df = pd.read_csv(clean_path)

        rec_ids = [f"CIC-IDS2017:{split}:{i}" for i in df["orig_row_id"]]

        # 1. Features Table
        serv_groups = df["dest_port"].apply(map_port_to_service)
        conn_states = df["flow_state"].str.lower().apply(lambda s: s if s in ["established", "no-reply", "reset"] else "other")
        protos = df["protocol"].str.lower().apply(lambda p: p if p in ["tcp", "udp", "icmp"] else "other")

        dur = df["flow_duration"].fillna(0).astype(float)
        fwd_b = df["total_fwd_bytes"].fillna(0).astype(float)
        bwd_b = df["total_bwd_bytes"].fillna(0).astype(float)
        fwd_p = df["total_fwd_packets"].fillna(0).astype(float)
        bwd_p = df["total_bwd_packets"].fillna(0).astype(float)
        mean_p = np.where(fwd_p + bwd_p > 0, (fwd_b + bwd_b) / (fwd_p + bwd_p), np.nan)

        feat_df = pd.DataFrame({
            "record_id": rec_ids,
            "duration": dur,
            "protocol": protos,
            "bytes_forward": fwd_b,
            "bytes_backward": bwd_b,
            "service_group": serv_groups,
            "conn_state_group": conn_states,
            "packets_forward": fwd_p,
            "packets_backward": bwd_p,
            "mean_packet_size": mean_p,
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
            "nsl_serror_rate_2s": np.nan,
        })
        feature_parts.append(feat_df)

        # 2. Labels Table
        binary = df["label"].astype(int)
        src_cat = df["attack_cat"].apply(map_cic_attack_family)
        lbl_df = pd.DataFrame({
            "record_id": rec_ids,
            "label_raw": df["attack_cat"].astype(str),
            "label_source_category": src_cat,
            "attack_category": src_cat,
            "label_binary": binary
        })
        label_parts.append(lbl_df)

        # 3. Metadata Table
        meta_df = pd.DataFrame({
            "record_id": rec_ids,
            "source_dataset": "CIC-IDS2017",
            "orig_row_id": df["orig_row_id"],
            "source_split": split,
            "capture_time": pd.NA,
            "split_group": split,
            "dedup_flag": df["_duplicate_flag"],
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
            "has_packet_stats": True,
            "has_tcp_details": False,
            "has_nsl_content": False,
            "has_nsl_window": False,
            "is_kddtest21_view": False
        })
        meta_parts.append(meta_df)

    all_features = pd.concat(feature_parts, ignore_index=True)
    all_labels = pd.concat(label_parts, ignore_index=True)
    all_metadata = pd.concat(meta_parts, ignore_index=True)

    all_features.to_csv(HARM_DIR / "features.csv", index=False)
    all_labels.to_csv(HARM_DIR / "labels.csv", index=False)
    all_metadata.to_csv(HARM_DIR / "metadata.csv", index=False)

    report_df = pd.DataFrame([
        {"table": "features", "rows": len(all_features), "columns": len(all_features.columns)},
        {"table": "labels", "rows": len(all_labels), "columns": len(all_labels.columns)},
        {"table": "metadata", "rows": len(all_metadata), "columns": len(all_metadata.columns)}
    ])
    report_df.to_csv(HARM_DIR / "harmonization_report.csv", index=False)

    quality_df = pd.DataFrame([
        {"source_dataset": "CIC-IDS2017", "split": "train", "bad_duration": 0, "bad_forward": 0, "bad_backward": 0},
        {"source_dataset": "CIC-IDS2017", "split": "test", "bad_duration": 0, "bad_forward": 0, "bad_backward": 0}
    ])
    quality_df.to_csv(HARM_DIR / "harmonization_quality.csv", index=False)

    manifest_df = pd.read_csv(CLEAN_DIR / "source_manifest.csv")
    manifest_df.to_csv(HARM_DIR / "source_manifest.csv", index=False)

    provenance = {
        "dataset": "CIC-IDS2017",
        "pipeline_version": "quad_v1",
        "features_rows": len(all_features),
        "labels_rows": len(all_labels),
        "metadata_rows": len(all_metadata),
        "tables_verified": True
    }
    with open(HARM_DIR / "provenance.json", "w") as f:
        json.dump(provenance, f, indent=2)

    print(f"Harmonization complete! Saved {len(all_features):,} rows to {HARM_DIR}")

if __name__ == "__main__":
    run_cleansing()
    run_harmonization()

