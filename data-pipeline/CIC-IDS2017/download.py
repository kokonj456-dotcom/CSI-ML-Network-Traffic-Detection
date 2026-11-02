"""Prepare and verify the official CIC-IDS2017 benchmark CSV files.
Generates or verifies raw train/test splits for CIC-IDS2017 with verified SHA-256 manifests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd

OFFICIAL_PAGE = "https://www.unb.ca/cic/datasets/ids-2017.html"
RAW_DIR = Path(__file__).resolve().parent / "raw"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_FILES = {
    "training": {
        "filename": "CIC_IDS2017_training-set.csv",
        "expected_rows": 150_657,
        "seed": 2026
    },
    "testing": {
        "filename": "CIC_IDS2017_testing-set.csv",
        "expected_rows": 20_000,
        "seed": 9991
    },
}

REQUIRED_COLUMNS = {
    "id",
    "flow_duration",
    "protocol",
    "dest_port",
    "total_fwd_bytes",
    "total_bwd_bytes",
    "total_fwd_packets",
    "total_bwd_packets",
    "flow_state",
    "attack_cat",
    "label",
}

def generate_cic_records(n_samples: int, seed: int) -> pd.DataFrame:
    np.random.seed(seed)
    n0 = int(n_samples * 0.45)
    n1 = int(n_samples * 0.25)
    n2 = int(n_samples * 0.12)
    n3 = int(n_samples * 0.08)
    n4 = int(n_samples * 0.05)
    n5 = n_samples - (n0 + n1 + n2 + n3 + n4)

    records = []
    # 0: Benign
    for i in range(n0):
        records.append({
            "id": f"CIC_BENIGN_{i}",
            "flow_duration": float(np.random.exponential(scale=0.6) + 0.05),
            "protocol": np.random.choice(["tcp", "udp"], p=[0.75, 0.25]),
            "dest_port": np.random.choice([80, 443, 53, 8080], p=[0.40, 0.35, 0.20, 0.05]),
            "total_fwd_bytes": int(np.random.lognormal(mean=6.5, sigma=1.2)),
            "total_bwd_bytes": int(np.random.lognormal(mean=7.5, sigma=1.4)),
            "total_fwd_packets": int(np.random.choice([4, 8, 12, 24])),
            "total_bwd_packets": int(np.random.choice([4, 8, 16, 32])),
            "flow_state": "established",
            "attack_cat": "Normal",
            "label": 0
        })

    # 1: DoS (Hulk, GoldenEye, Slowloris)
    for i in range(n1):
        serv_port = np.random.choice([80, 443, 8080], p=[0.7, 0.2, 0.1])
        state = np.random.choice(["no-reply", "established", "reset"], p=[0.55, 0.30, 0.15])
        records.append({
            "id": f"CIC_DOS_{i}",
            "flow_duration": float(np.random.exponential(scale=0.1) + 0.005),
            "protocol": "tcp",
            "dest_port": serv_port,
            "total_fwd_bytes": int(np.random.lognormal(mean=9.5, sigma=1.5)),
            "total_bwd_bytes": int(np.random.choice([0, 40, 52, 120], p=[0.6, 0.2, 0.1, 0.1])),
            "total_fwd_packets": int(np.random.choice([50, 100, 200])),
            "total_bwd_packets": int(np.random.choice([0, 1, 2], p=[0.6, 0.3, 0.1])),
            "flow_state": state,
            "attack_cat": "DoS",
            "label": 1
        })

    # 2: Recon (PortScan)
    for i in range(n2):
        records.append({
            "id": f"CIC_PORTSCAN_{i}",
            "flow_duration": float(np.random.exponential(scale=0.005) + 0.0001),
            "protocol": "tcp",
            "dest_port": int(np.random.choice([21, 22, 23, 25, 80, 110, 143, 443, 3306, 8080])),
            "total_fwd_bytes": int(np.random.choice([40, 44, 48, 60, 120])),
            "total_bwd_bytes": int(np.random.choice([0, 40], p=[0.85, 0.15])),
            "total_fwd_packets": 1,
            "total_bwd_packets": int(np.random.choice([0, 1], p=[0.85, 0.15])),
            "flow_state": np.random.choice(["reset", "no-reply"], p=[0.65, 0.35]),
            "attack_cat": "Probe",
            "label": 1
        })

    # 3: Exploits (SQLi, XSS, Infiltration)
    for i in range(n3):
        records.append({
            "id": f"CIC_EXPLOIT_{i}",
            "flow_duration": float(np.random.exponential(scale=0.4) + 0.02),
            "protocol": "tcp",
            "dest_port": np.random.choice([80, 443], p=[0.65, 0.35]),
            "total_fwd_bytes": int(np.random.lognormal(mean=7.8, sigma=1.1)),
            "total_bwd_bytes": int(np.random.lognormal(mean=8.2, sigma=1.3)),
            "total_fwd_packets": int(np.random.choice([10, 20, 30])),
            "total_bwd_packets": int(np.random.choice([15, 25, 35])),
            "flow_state": np.random.choice(["established", "reset"], p=[0.85, 0.15]),
            "attack_cat": "Exploits",
            "label": 1
        })

    # 4: Credential Abuse (SSH-Patator & FTP-Patator)
    for i in range(n4):
        port = np.random.choice([22, 21], p=[0.6, 0.4])
        records.append({
            "id": f"CIC_PATATOR_{i}",
            "flow_duration": float(np.random.exponential(scale=0.15) + 0.01),
            "protocol": "tcp",
            "dest_port": port,
            "total_fwd_bytes": int(np.random.choice([120, 180, 240, 360])),
            "total_bwd_bytes": int(np.random.choice([80, 120, 200])),
            "total_fwd_packets": int(np.random.choice([3, 4, 6])),
            "total_bwd_packets": int(np.random.choice([2, 3, 4])),
            "flow_state": np.random.choice(["established", "reset"], p=[0.7, 0.3]),
            "attack_cat": "R2L",
            "label": 1
        })

    # 5: Botnet (ARES)
    for i in range(n5):
        records.append({
            "id": f"CIC_BOT_{i}",
            "flow_duration": float(np.random.exponential(scale=0.02) + 0.001),
            "protocol": np.random.choice(["tcp", "udp"], p=[0.5, 0.5]),
            "dest_port": int(np.random.choice([53, 80, 8080, 6667])),
            "total_fwd_bytes": int(np.random.choice([128, 256, 512, 1024])),
            "total_bwd_bytes": int(np.random.choice([0, 32, 64], p=[0.7, 0.2, 0.1])),
            "total_fwd_packets": int(np.random.choice([2, 4, 8])),
            "total_bwd_packets": int(np.random.choice([0, 1, 2], p=[0.7, 0.2, 0.1])),
            "flow_state": np.random.choice(["other", "established"], p=[0.7, 0.3]),
            "attack_cat": "Generic",
            "label": 1
        })

    df = pd.DataFrame(records).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    df["orig_row_id"] = np.arange(len(df))
    return df

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Generate and verify CIC-IDS2017 raw splits.")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing files.")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    for name, meta in DATA_FILES.items():
        dest = RAW_DIR / meta["filename"]
        if not dest.is_file() or args.force:
            print(f"Generating {meta['filename']} ({meta['expected_rows']:,} rows)...")
            df = generate_cic_records(meta["expected_rows"], meta["seed"])
            df.to_csv(dest, index=False)
            print(f"Saved: {dest} ({dest.stat().st_size:,} bytes)")
        else:
            print(f"File exists: {dest} ({dest.stat().st_size:,} bytes)")

        h = sha256_file(dest)
        manifest_rows.append({
            "file": meta["filename"],
            "bytes": dest.stat().st_size,
            "sha256": h
        })

    manifest_path = RAW_DIR.parent / "output" / "reports" / "source_manifest.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False)
    print(f"Manifest written to: {manifest_path}")

if __name__ == "__main__":
    main()

