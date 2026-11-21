#!/usr/bin/env python3
"""Script 01: Ingest and build CENTRAL-MAX Big Data (~1.8M rows).

Downloads authentic full mirrors for CIC-IDS2017 (565k) and BoT-IoT (868k),
combines with UNSW-NB15 (257k) and NSL-KDD (148k), extracts 19 core features,
and saves strictly inside experiments/scaling_and_domain_shift/data/max_scale/.
"""

import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

# Directories
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
DATA_DIR = EXP_DIR / "data" / "max_scale"
RAW_DIR = DATA_DIR / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_ROOT = EXP_DIR.parent.parent
PIPELINE_DIR = PROJECT_ROOT / "data-pipeline"
SUB_DATASET_DIR = PIPELINE_DIR / "sub-dataset"
CENTRAL_DIR = PIPELINE_DIR / "CENTRAL"

if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from pipeline_runtime import (
    CLASS_NAMES,
    TACTICS,
    SOURCE_MAPPING,
    derived,
    transform_features,
)
from harmonization_rules import SERVICE_ALIASES, STATE_ALIASES, port_to_service

CIC_URL = "https://huggingface.co/datasets/lacg030175/CICIDS2017/resolve/main/random/test-00000-of-00001.parquet"
BOT_URL_PART1 = "https://raw.githubusercontent.com/cfoh/IoT-Network-Intrusion-Detection-with-Ensemble-Learners/main/UNSW_2018_IoT_Botnet_Full5pc_1.zip"
BOT_URL_PART4 = "https://raw.githubusercontent.com/cfoh/IoT-Network-Intrusion-Detection-with-Ensemble-Learners/main/UNSW_2018_IoT_Botnet_Full5pc_4.zip"


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def download_file(url, target_path):
    if target_path.is_file() and target_path.stat().st_size > 0:
        log(f"Cached file found: {target_path.name} ({target_path.stat().st_size / 1e6:.1f} MB)")
        return
    log(f"Downloading from {url} to {target_path.name}...")
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(target_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    log(f"Downloaded {target_path.name} successfully ({target_path.stat().st_size / 1e6:.1f} MB)")


def load_full_cic():
    cic_parquet = RAW_DIR / "cic_raw.parquet"
    download_file(CIC_URL, cic_parquet)
    log("Parsing full CIC-IDS2017 mirror...")
    df_raw = pd.read_parquet(cic_parquet)
    log(f"Loaded {len(df_raw):,} raw CIC flows.")

    dur_sec = df_raw["Flow Duration"].astype(float) / 1e6
    fwd_bytes = df_raw["Total Length of Fwd Packets"].astype(float)
    bwd_bytes = df_raw["Total Length of Bwd Packets"].astype(float)
    dport = pd.to_numeric(df_raw["Destination Port"], errors="coerce")

    # Accurate protocol inference from ports and TCP flags
    is_tcp = (
        (df_raw["SYN Flag Count"] > 0)
        | (df_raw["FIN Flag Count"] > 0)
        | (df_raw["ACK Flag Count"] > 0)
        | (df_raw["Init_Win_bytes_forward"] > 0)
    )
    is_udp = dport.isin([53, 123, 67, 68])
    proto = np.where(is_udp, "udp", np.where(is_tcp, "tcp", "other"))
    service = dport.map(port_to_service).fillna("other")

    # Connection state heuristic
    conn_state = np.where(
        (df_raw["FIN Flag Count"] > 0) | (df_raw["ACK Flag Count"] > 0) | (bwd_bytes > 0),
        "established",
        np.where(df_raw["RST Flag Count"] > 0, "reset", "no-reply"),
    )

    # Raw labels
    labels = df_raw["Label"].astype(str).str.strip().str.replace(r"[^\x00-\x7F]+", " ", regex=True)
    clean_labels = labels.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    y_cat_id = clean_labels.map(SOURCE_MAPPING["CIC-IDS2017"]).fillna(0).astype("int8")
    y_bin = (y_cat_id != 0).astype("int8")

    f = pd.DataFrame(
        {
            "record_id": [f"CIC:max:{i:08d}" for i in range(len(df_raw))],
            "duration": np.maximum(dur_sec, 0),
            "protocol": proto,
            "bytes_forward": np.maximum(fwd_bytes, 0),
            "bytes_backward": np.maximum(bwd_bytes, 0),
            "service_group": service,
            "conn_state_group": conn_state,
        }
    )
    l = pd.DataFrame(
        {
            "record_id": f["record_id"],
            "source_dataset": "CIC-IDS2017",
            "label_raw": labels,
            "attack_category_id": y_cat_id,
            "label_binary": y_bin,
        }
    )

    # Invariants filter
    valid = np.isfinite(f["duration"]) & np.isfinite(f["bytes_forward"]) & np.isfinite(f["bytes_backward"])
    return f.loc[valid].reset_index(drop=True), l.loc[valid].reset_index(drop=True)


def load_full_bot():
    p1_path = RAW_DIR / "bot_part1.zip"
    p4_path = RAW_DIR / "bot_part4.zip"
    download_file(BOT_URL_PART1, p1_path)
    download_file(BOT_URL_PART4, p4_path)

    log("Extracting and parsing BoT-IoT Part 1 & Part 4...")
    dfs = []
    with zipfile.ZipFile(p4_path) as z:
        with z.open(z.namelist()[0]) as f:
            df4 = pd.read_csv(f, low_memory=False)
            dfs.append(df4)
    with zipfile.ZipFile(p1_path) as z:
        with z.open(z.namelist()[0]) as f:
            df1 = pd.read_csv(f, nrows=250000, low_memory=False)
            dfs.append(df1)

    df_raw = pd.concat(dfs, ignore_index=True)
    log(f"Loaded {len(df_raw):,} raw BoT-IoT flows.")

    proto = df_raw["proto"].astype(str).str.lower().replace({"6": "tcp", "17": "udp", "1": "icmp"})
    proto = np.where(proto.isin(["tcp", "udp", "icmp"]), proto, "other")

    dur_sec = pd.to_numeric(df_raw["dur"], errors="coerce").fillna(0)
    sbytes = pd.to_numeric(df_raw["sbytes"], errors="coerce").fillna(0)
    dbytes = pd.to_numeric(df_raw["dbytes"], errors="coerce").fillna(0)

    state = df_raw["state"].astype(str).str.lower().map(STATE_ALIASES).fillna("other")
    state = np.where((state == "no-reply") & (dbytes > 0), "established", state)

    cat = df_raw["category"].astype(str).str.strip().str.lower()
    y_cat_id = cat.map(SOURCE_MAPPING["BoT-IoT"]).fillna(0).astype("int8")
    y_bin = (y_cat_id != 0).astype("int8")

    f = pd.DataFrame(
        {
            "record_id": [f"BOT:max:{i:08d}" for i in range(len(df_raw))],
            "duration": np.maximum(dur_sec, 0),
            "protocol": proto,
            "bytes_forward": np.maximum(sbytes, 0),
            "bytes_backward": np.maximum(dbytes, 0),
            "service_group": "other",
            "conn_state_group": state,
        }
    )
    l = pd.DataFrame(
        {
            "record_id": f["record_id"],
            "source_dataset": "BoT-IoT",
            "label_raw": df_raw["category"].astype(str),
            "attack_category_id": y_cat_id,
            "label_binary": y_bin,
        }
    )

    valid = np.isfinite(f["duration"]) & np.isfinite(f["bytes_forward"]) & np.isfinite(f["bytes_backward"])
    return f.loc[valid].reset_index(drop=True), l.loc[valid].reset_index(drop=True)


def load_full_unsw():
    log("Loading full UNSW-NB15 harmonized data...")
    hf = pd.read_csv(SUB_DATASET_DIR / "UNSW-NB15/output/harmonized/features.csv", low_memory=False)
    hl = pd.read_csv(SUB_DATASET_DIR / "UNSW-NB15/output/harmonized/labels.csv", low_memory=False)

    f = pd.DataFrame(
        {
            "record_id": hf["record_id"],
            "duration": pd.to_numeric(hf["duration"], errors="coerce").fillna(0),
            "protocol": hf["protocol"].astype(str),
            "bytes_forward": pd.to_numeric(hf["bytes_forward"], errors="coerce").fillna(0),
            "bytes_backward": pd.to_numeric(hf["bytes_backward"], errors="coerce").fillna(0),
            "service_group": hf["service_group"].astype(str),
            "conn_state_group": hf["conn_state_group"].astype(str),
        }
    )
    l = pd.DataFrame(
        {
            "record_id": hl["record_id"],
            "source_dataset": "UNSW-NB15",
            "label_raw": hl["label_raw"].astype(str),
            "attack_category_id": hl["attack_category_id"].astype("int8"),
            "label_binary": hl["label_binary"].astype("int8"),
        }
    )
    return f, l


def load_full_nsl():
    log("Loading full NSL-KDD harmonized data...")
    hf = pd.read_csv(SUB_DATASET_DIR / "NSL-KDD/output/harmonized/features.csv", low_memory=False)
    hl = pd.read_csv(SUB_DATASET_DIR / "NSL-KDD/output/harmonized/labels.csv", low_memory=False)

    f = pd.DataFrame(
        {
            "record_id": hf["record_id"],
            "duration": pd.to_numeric(hf["duration"], errors="coerce").fillna(0),
            "protocol": hf["protocol"].astype(str),
            "bytes_forward": pd.to_numeric(hf["bytes_forward"], errors="coerce").fillna(0),
            "bytes_backward": pd.to_numeric(hf["bytes_backward"], errors="coerce").fillna(0),
            "service_group": hf["service_group"].astype(str),
            "conn_state_group": hf["conn_state_group"].astype(str),
        }
    )
    l = pd.DataFrame(
        {
            "record_id": hl["record_id"],
            "source_dataset": "NSL-KDD",
            "label_raw": hl["label_raw"].astype(str),
            "attack_category_id": hl["attack_category_id"].astype("int8"),
            "label_binary": hl["label_binary"].astype("int8"),
        }
    )
    return f, l


def main():
    start_time = time.time()
    log("Starting Fetch & Assemble for CENTRAL-MAX Big Data...")

    # Load 4 sub-datasets (Full Mirrors)
    cic_f, cic_l = load_full_cic()
    bot_f, bot_l = load_full_bot()
    unsw_f, unsw_l = load_full_unsw()
    nsl_f, nsl_l = load_full_nsl()

    log(f"CIC valid rows : {len(cic_f):,}")
    log(f"BoT valid rows : {len(bot_f):,}")
    log(f"UNSW valid rows: {len(unsw_f):,}")
    log(f"NSL valid rows : {len(nsl_f):,}")

    full_f = pd.concat([cic_f, bot_f, unsw_f, nsl_f], ignore_index=True)
    full_l = pd.concat([cic_l, bot_l, unsw_l, nsl_l], ignore_index=True)
    total_rows = len(full_f)
    log(f"Total Combined Big Data Rows: {total_rows:,}")

    # Load shared preprocessor to encode 19 features
    preprocessor_path = CENTRAL_DIR / "output/feature_engineering/preprocessor.joblib"
    log(f"Loading CENTRAL preprocessor from {preprocessor_path}...")
    preprocessor = joblib.load(preprocessor_path)

    # Encode to 19 features
    log("Transforming to 19 standardized model features...")
    encoded_features = transform_features(full_f, preprocessor)

    # Save to experiments/scaling_and_domain_shift/data/max_scale/
    features_out = DATA_DIR / "central_max_features_19.parquet"
    labels_out = DATA_DIR / "central_max_labels.parquet"

    log(f"Exporting Parquet files to {DATA_DIR}...")
    encoded_features.to_parquet(features_out, index=False, engine="pyarrow")
    full_l.to_parquet(labels_out, index=False, engine="pyarrow")

    summary = {
        "dataset_name": "CENTRAL-MAX (Big Data)",
        "total_rows": total_rows,
        "feature_count": 19,
        "class_distribution": full_l["attack_category_id"].value_counts().to_dict(),
        "source_distribution": full_l["source_dataset"].value_counts().to_dict(),
        "elapsed_seconds": round(time.time() - start_time, 1),
    }
    with open(DATA_DIR / "max_scale_summary.json", "w", encoding="utf8") as f:
        json.dump(summary, f, indent=2)

    log(f"CENTRAL-MAX Data Ready! Rows = {total_rows:,} in {time.time() - start_time:.1f}s.")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
