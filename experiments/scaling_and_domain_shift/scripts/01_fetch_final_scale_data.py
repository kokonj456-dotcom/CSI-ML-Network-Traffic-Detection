#!/usr/bin/env python3
"""Script 01: Ingest and build CENTRAL-FINAL Big Data (5.0M+ rows).

Combines authentic multi-domain network flows from 6 diverse datasets:
1. NSL-KDD (148,517 rows) - Legacy/historic baseline
2. UNSW-NB15 (257,673 rows) - Modern enterprise network
3. BoT-IoT (Parts 1-4, ~1,800,000 rows sampled) - IoT botnets & DoS/Recon
4. CIC-IDS2017 Full Train (2,000,000 rows sampled) - Enterprise Canadian LAN
5. CIC-IDS2018 AWS Cloud (619,346 rows) - AWS cloud infrastructure (Bruteforce)
6. ToN-IoT Zeek/Bro (211,043 rows) - Industrial & IoT modern attacks

Harmonizes all into 19 standardized physical flow features and 6 MITRE ATT&CK classes
in strict compliance with pipeline_runtime.SOURCE_MAPPING and CLASS_NAMES.
Saves strictly inside experiments/scaling_and_domain_shift/data/final_scale/.
"""

import gc
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
DATA_DIR = EXP_DIR / "data" / "final_scale"
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
    transform_features,
)
from harmonization_rules import STATE_ALIASES, port_to_service


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def sanitize_dataframe(df):
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype("string")
    return df


def load_nsl():
    log("Loading NSL-KDD harmonized data...")
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
    log(f"  Loaded NSL-KDD: {len(f):,} rows")
    return f, l


def load_unsw():
    log("Loading UNSW-NB15 harmonized data...")
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
    log(f"  Loaded UNSW-NB15: {len(f):,} rows")
    return f, l


def load_bot_all(target_rows=1_800_000):
    log("Loading BoT-IoT Parts 1-4...")
    dfs = []
    for part in [1, 2, 3, 4]:
        zf_path = RAW_DIR / f"bot_part{part}.zip"
        if not zf_path.exists():
            log(f"  Warning: {zf_path} missing!")
            continue
        with zipfile.ZipFile(zf_path) as z:
            csv_name = [n for n in z.namelist() if n.endswith(".csv")][0]
            with z.open(csv_name) as f:
                nrows = 450_000 if part < 4 else None
                df = pd.read_csv(f, nrows=nrows, low_memory=False)
                dfs.append(df)
                log(f"  Loaded BoT-IoT Part {part}: {len(df):,} rows")

    df_raw = pd.concat(dfs, ignore_index=True)
    log(f"  Total Raw BoT-IoT flows: {len(df_raw):,}")

    proto = df_raw["proto"].astype(str).str.lower().replace({"6": "tcp", "17": "udp", "1": "icmp"})
    proto = np.where(proto.isin(["tcp", "udp", "icmp"]), proto, "other")

    dur_sec = pd.to_numeric(df_raw["dur"], errors="coerce").fillna(0)
    sbytes = pd.to_numeric(df_raw["sbytes"], errors="coerce").fillna(0)
    dbytes = pd.to_numeric(df_raw["dbytes"], errors="coerce").fillna(0)

    state = df_raw["state"].astype(str).str.lower().map(STATE_ALIASES).fillna("other")
    state = np.where((state == "no-reply") & (dbytes > 0), "established", state)

    # MITRE ATT&CK Standard Mapping:
    # DoS/DDoS -> 1
    # Reconnaissance -> 2
    # Normal -> 0
    cat = df_raw["category"].astype(str).str.strip().str.lower()
    y_cat_id = cat.map(SOURCE_MAPPING["BoT-IoT"]).fillna(0).astype("int8")
    y_bin = (y_cat_id != 0).astype("int8")

    rec_ids = [f"BOT:final:{i:08d}" for i in range(len(df_raw))]

    f = pd.DataFrame(
        {
            "record_id": rec_ids,
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
            "record_id": rec_ids,
            "source_dataset": "BoT-IoT",
            "label_raw": df_raw["category"].astype(str),
            "attack_category_id": y_cat_id,
            "label_binary": y_bin,
        }
    )

    valid = np.isfinite(f["duration"]) & np.isfinite(f["bytes_forward"]) & np.isfinite(f["bytes_backward"])
    f = f.loc[valid].reset_index(drop=True)
    l = l.loc[valid].reset_index(drop=True)

    if len(f) > target_rows:
        log(f"  Sampling BoT-IoT down to {target_rows:,} rows (preserving all normal & recon)...")
        m_norm = l["attack_category_id"] == 0
        m_recon = l["attack_category_id"] == 2
        m_dos = l["attack_category_id"] == 1

        idx_norm = l[m_norm].index
        idx_recon = l[m_recon].index
        remain = target_rows - len(idx_norm) - len(idx_recon)
        idx_dos = l[m_dos].sample(n=min(remain, m_dos.sum()), random_state=42).index
        selected_idx = np.sort(np.concatenate([idx_norm, idx_recon, idx_dos]))

        f = f.loc[selected_idx].reset_index(drop=True)
        l = l.loc[selected_idx].reset_index(drop=True)

    log(f"  Total BoT-IoT selected: {len(f):,} rows")
    return f, l


def load_cic2017(target_rows=2_000_000):
    log("Loading CIC-IDS2017 Full Train Data...")
    p_path = RAW_DIR / "cic2017_train.parquet"
    if not p_path.exists():
        p_path = RAW_DIR / "cic_raw.parquet"
        log("  Falling back to cached cic_raw.parquet")

    df_raw = pd.read_parquet(p_path)
    log(f"  Raw CIC-IDS2017 loaded: {len(df_raw):,} rows")

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

    # Raw labels & MITRE ATT&CK Standard Mapping from SOURCE_MAPPING
    labels = df_raw["Label"].astype(str).str.strip().str.replace(r"[^\x00-\x7F]+", " ", regex=True)
    clean_labels = labels.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    y_cat_id = clean_labels.map(SOURCE_MAPPING["CIC-IDS2017"]).fillna(0).astype("int8")
    y_bin = (y_cat_id != 0).astype("int8")

    rec_ids = [f"CIC:final:{i:08d}" for i in range(len(df_raw))]

    f = pd.DataFrame(
        {
            "record_id": rec_ids,
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
            "record_id": rec_ids,
            "source_dataset": "CIC-IDS2017",
            "label_raw": labels,
            "attack_category_id": y_cat_id,
            "label_binary": y_bin,
        }
    )

    valid = np.isfinite(f["duration"]) & np.isfinite(f["bytes_forward"]) & np.isfinite(f["bytes_backward"])
    f = f.loc[valid].reset_index(drop=True)
    l = l.loc[valid].reset_index(drop=True)

    if len(f) > target_rows:
        log(f"  Sampling CIC-IDS2017 down to {target_rows:,} rows (preserving all rare attacks)...")
        m_benign = l["label_binary"] == 0
        idx_att = l[~m_benign].index
        remain = target_rows - len(idx_att)
        idx_benign = l[m_benign].sample(n=min(remain, m_benign.sum()), random_state=42).index
        selected_idx = np.sort(np.concatenate([idx_att, idx_benign]))

        f = f.loc[selected_idx].reset_index(drop=True)
        l = l.loc[selected_idx].reset_index(drop=True)

    log(f"  Total CIC-IDS2017 selected: {len(f):,} rows")
    return f, l


def load_cic2018():
    log("Loading CIC-IDS2018 AWS Cloud Data...")
    p_path = RAW_DIR / "cic2018_bruteforce.parquet"
    if not p_path.exists():
        log(f"  Warning: {p_path} missing!")
        return pd.DataFrame(), pd.DataFrame()

    df_raw = pd.read_parquet(p_path)
    log(f"  Raw CIC-IDS2018 loaded: {len(df_raw):,} rows")

    dur_sec = pd.to_numeric(df_raw["Flow Duration"], errors="coerce").fillna(0) / 1e6
    dur_sec = np.clip(dur_sec, 0, None)
    sbytes = pd.to_numeric(df_raw["Fwd Packets Length Total"], errors="coerce").fillna(0)
    dbytes = pd.to_numeric(df_raw["Bwd Packets Length Total"], errors="coerce").fillna(0)

    proto_num = df_raw["Protocol"].astype(int)
    proto = np.where(proto_num == 6, "tcp", np.where(proto_num == 17, "udp", np.where(proto_num == 1, "icmp", "other")))

    conn_state = np.where(
        (df_raw["FIN Flag Count"] > 0) | (df_raw["ACK Flag Count"] > 0) | (dbytes > 0),
        "established",
        np.where(df_raw["RST Flag Count"] > 0, "reset", "no-reply"),
    )

    label_raw = df_raw["Label"].astype(str).str.strip()
    # MITRE ATT&CK: SSH/FTP Bruteforce -> Class 4 (Credential Abuse)
    y_cat_id = np.where(label_raw.str.contains("Bruteforce|BruteForce", case=False), 4, 0).astype("int8")
    y_bin = (y_cat_id != 0).astype("int8")

    service = np.full(len(df_raw), "other", dtype=object)
    service[label_raw.str.contains("SSH", case=False)] = "ssh"
    service[label_raw.str.contains("FTP", case=False)] = "ftp"

    rec_ids = [f"CIC18:final:{i:08d}" for i in range(len(df_raw))]

    f = pd.DataFrame(
        {
            "record_id": rec_ids,
            "duration": dur_sec,
            "protocol": proto,
            "bytes_forward": sbytes,
            "bytes_backward": dbytes,
            "service_group": service,
            "conn_state_group": conn_state,
        }
    )
    l = pd.DataFrame(
        {
            "record_id": rec_ids,
            "source_dataset": "CIC-IDS2018",
            "label_raw": label_raw,
            "attack_category_id": y_cat_id,
            "label_binary": y_bin,
        }
    )
    valid = np.isfinite(f["duration"]) & np.isfinite(f["bytes_forward"]) & np.isfinite(f["bytes_backward"])
    log(f"  Loaded CIC-IDS2018: {valid.sum():,} rows")
    return f.loc[valid].reset_index(drop=True), l.loc[valid].reset_index(drop=True)


def load_ton_iot():
    log("Loading ToN-IoT Zeek/Bro Data...")
    csv_path = RAW_DIR / "ton_iot.csv"
    if not csv_path.exists():
        log(f"  Warning: {csv_path} missing!")
        return pd.DataFrame(), pd.DataFrame()

    df = pd.read_csv(csv_path, low_memory=False)
    log(f"  Raw ToN-IoT loaded: {len(df):,} rows")

    dur = np.clip(pd.to_numeric(df["duration"], errors="coerce").fillna(0), 0, None)
    sbytes = np.clip(pd.to_numeric(df["src_bytes"], errors="coerce").fillna(0), 0, None)
    dbytes = np.clip(pd.to_numeric(df["dst_bytes"], errors="coerce").fillna(0), 0, None)

    proto = df["proto"].astype(str).str.lower().str.strip()
    proto_mapped = np.where(proto.isin(["tcp", "udp", "icmp"]), proto, "other")

    serv = df["service"].astype(str).str.lower().str.strip()
    serv_mapped = np.where(
        serv.isin(["dns", "ftp", "http", "smtp", "ssh"]),
        serv,
        np.where(serv.isin(["ssl", "https"]), "https_ssl", "other"),
    )

    st = df["conn_state"].astype(str).str.upper().str.strip()
    state_mapped = np.where(
        st.isin(["SF", "S1", "S2", "S3", "ESTABLISHED"]),
        "established",
        np.where(st.isin(["S0", "SH", "SHR"]), "no-reply", np.where(st.isin(["REJ", "RSTO", "RSTR", "RSTOS0"]), "reset", "other")),
    )

    label_type = df["type"].astype(str).str.lower().str.strip()
    # MITRE ATT&CK Standard Mapping for ToN-IoT:
    # 0: normal
    # 1: Denial of Service (dos, ddos)
    # 2: Reconnaissance & Probing (scanning)
    # 3: Exploits & PrivEsc (injection, ransomware, xss)
    # 4: Credential Abuse (password)
    # 5: Malware, C2 & Botnet (backdoor, mitm)
    att_id = np.zeros(len(df), dtype=np.int8)
    att_id[label_type.isin(["dos", "ddos"])] = 1
    att_id[label_type == "scanning"] = 2
    att_id[label_type.isin(["injection", "ransomware", "xss"])] = 3
    att_id[label_type == "password"] = 4
    att_id[label_type.isin(["backdoor", "mitm"])] = 5
    y_bin = (att_id != 0).astype("int8")

    rec_ids = [f"TON:final:{i:08d}" for i in range(len(df))]

    f = pd.DataFrame(
        {
            "record_id": rec_ids,
            "duration": dur,
            "protocol": proto_mapped,
            "bytes_forward": sbytes,
            "bytes_backward": dbytes,
            "service_group": serv_mapped,
            "conn_state_group": state_mapped,
        }
    )
    l = pd.DataFrame(
        {
            "record_id": rec_ids,
            "source_dataset": "ToN-IoT",
            "label_raw": label_type,
            "attack_category_id": att_id,
            "label_binary": y_bin,
        }
    )
    valid = np.isfinite(f["duration"]) & np.isfinite(f["bytes_forward"]) & np.isfinite(f["bytes_backward"])
    log(f"  Loaded ToN-IoT: {valid.sum():,} rows")
    return f.loc[valid].reset_index(drop=True), l.loc[valid].reset_index(drop=True)


def main():
    start_time = time.time()
    log("==================================================================")
    log("Starting Fetch & Assemble for CENTRAL-FINAL Big Data (5.0M+ Rows)")
    log("==================================================================")

    # Load 6 sub-datasets
    nsl_f, nsl_l = load_nsl()
    unsw_f, unsw_l = load_unsw()
    ton_f, ton_l = load_ton_iot()
    cic18_f, cic18_l = load_cic2018()
    bot_f, bot_l = load_bot_all(target_rows=1_800_000)
    cic17_f, cic17_l = load_cic2017(target_rows=2_000_000)

    log("\n--- Dataset Summary Counts ---")
    log(f"1. NSL-KDD    : {len(nsl_f):,} rows")
    log(f"2. UNSW-NB15  : {len(unsw_f):,} rows")
    log(f"3. ToN-IoT    : {len(ton_f):,} rows")
    log(f"4. CIC-IDS2018: {len(cic18_f):,} rows")
    log(f"5. BoT-IoT    : {len(bot_f):,} rows")
    log(f"6. CIC-IDS2017: {len(cic17_f):,} rows")

    full_f = pd.concat([nsl_f, unsw_f, ton_f, cic18_f, bot_f, cic17_f], ignore_index=True)
    full_l = pd.concat([nsl_l, unsw_l, ton_l, cic18_l, bot_l, cic17_l], ignore_index=True)

    total_rows = len(full_f)
    log(f"\nTotal Combined Big Data Rows: {total_rows:,}")
    assert total_rows >= 5_000_000, f"Expected >= 5,000,000 rows, got {total_rows:,}"

    # Load preprocessor to encode 19 features
    preprocessor_path = CENTRAL_DIR / "output/feature_engineering/preprocessor.joblib"
    log(f"Loading CENTRAL preprocessor from {preprocessor_path}...")
    preprocessor = joblib.load(preprocessor_path)

    log("Transforming to 19 standardized model features...")
    encoded_features = transform_features(full_f, preprocessor)
    encoded_features["record_id"] = full_f["record_id"]

    # Sanitize strings for Parquet
    encoded_features = sanitize_dataframe(encoded_features)
    full_l = sanitize_dataframe(full_l)

    metadata = pd.DataFrame(
        {
            "record_id": full_f["record_id"].astype("string"),
            "source_dataset": full_l["source_dataset"].astype("string"),
        }
    )

    # Save to final_scale directory
    features_out = DATA_DIR / "central_final_features_19.parquet"
    labels_out = DATA_DIR / "central_final_labels.parquet"
    metadata_out = DATA_DIR / "central_final_metadata.parquet"

    log(f"Exporting Parquet files to {DATA_DIR}...")
    encoded_features.to_parquet(features_out, index=False, engine="pyarrow")
    full_l.to_parquet(labels_out, index=False, engine="pyarrow")
    metadata.to_parquet(metadata_out, index=False, engine="pyarrow")

    log(f"Features: {features_out.name} ({features_out.stat().st_size / 1e6:.1f} MB)")
    log(f"Labels  : {labels_out.name} ({labels_out.stat().st_size / 1e6:.1f} MB)")
    log(f"Metadata: {metadata_out.name} ({metadata_out.stat().st_size / 1e6:.1f} MB)")

    # Print Class Distribution
    log("\nClass Distribution (MITRE ATT&CK):")
    counts = full_l["attack_category_id"].value_counts().sort_index()
    for cat_id, count in counts.items():
        name = CLASS_NAMES[cat_id] if 0 <= cat_id < len(CLASS_NAMES) else "Unknown"
        pct = count / total_rows * 100
        log(f"  Class {cat_id} ({name:25s}): {count:,} ({pct:.2f}%)")

    log(f"Normal Flows: {(full_l['label_binary'] == 0).sum():,} ({(full_l['label_binary'] == 0).mean()*100:.2f}%)")
    log(f"Attack Flows: {(full_l['label_binary'] == 1).sum():,} ({(full_l['label_binary'] == 1).mean()*100:.2f}%)")

    elapsed = round(time.time() - start_time, 2)
    log(f"\nStep 01 Complete! Assembled {total_rows:,} flows in {elapsed}s.")


if __name__ == "__main__":
    main()
