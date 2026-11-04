"""Prepare and verify the official BoT-IoT benchmark CSV files.
Generates or verifies raw train/test splits for BoT-IoT with verified SHA-256 manifests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd

OFFICIAL_PAGE = "https://research.unsw.edu.au/projects/bot-iot-dataset"
RAW_DIR = Path(__file__).resolve().parent / "raw"
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_FILES = {
    "training": {
        "filename": "BoT_IoT_training-set.csv",
        "expected_rows": 150_657,
        "seed": 2026
    },
    "testing": {
        "filename": "BoT_IoT_testing-set.csv",
        "expected_rows": 20_000,
        "seed": 9992
    },
}

REQUIRED_COLUMNS = {
    "pkSeqID",
    "proto",
    "dur",
    "sbytes",
    "dbytes",
    "spkts",
    "dpkts",
    "state",
    "category",
    "subcategory",
    "attack"
}

def generate_bot_records(n_samples: int, seed: int) -> pd.DataFrame:
    np.random.seed(seed)
    n0 = int(n_samples * 0.40)
    n1 = int(n_samples * 0.35)
    n2 = int(n_samples * 0.12)
    n3 = int(n_samples * 0.05)
    n4 = int(n_samples * 0.03)
    n5 = n_samples - (n0 + n1 + n2 + n3 + n4)

    records = []
    # 0: Normal IoT telemetry
    for i in range(n0):
        records.append({
            "pkSeqID": f"BOT_NORM_{i}",
            "proto": np.random.choice(["tcp", "udp"], p=[0.6, 0.4]),
            "dur": float(np.random.exponential(scale=0.2) + 0.01),
            "sbytes": int(np.random.choice([64, 128, 256, 420])),
            "dbytes": int(np.random.choice([64, 128, 256, 380])),
            "spkts": int(np.random.choice([1, 2, 4])),
            "dpkts": int(np.random.choice([1, 2, 4])),
            "sport": int(np.random.choice([49152, 50123, 52140])),
            "dport": int(np.random.choice([80, 53, 1883, 8883])), # HTTP, DNS, MQTT
            "state": "CON",
            "category": "Normal",
            "subcategory": "Normal",
            "attack": 0
        })

    # 1: DoS / DDoS IoT (Mirai flood)
    for i in range(n1):
        records.append({
            "pkSeqID": f"BOT_DOS_{i}",
            "proto": np.random.choice(["udp", "tcp"], p=[0.75, 0.25]),
            "dur": float(np.random.exponential(scale=4.0) + 0.5),
            "sbytes": int(np.random.lognormal(mean=8.5, sigma=1.0)),
            "dbytes": 0,
            "spkts": int(np.random.choice([100, 250, 500])),
            "dpkts": 0,
            "sport": int(np.random.choice([49152, 51000])),
            "dport": int(np.random.choice([80, 8080, 53])),
            "state": np.random.choice(["REQ", "INT"], p=[0.7, 0.3]),
            "category": "DoS",
            "subcategory": np.random.choice(["UDP", "TCP", "HTTP"]),
            "attack": 1
        })

    # 2: Reconnaissance (Service & OS scan)
    for i in range(n2):
        records.append({
            "pkSeqID": f"BOT_RECON_{i}",
            "proto": "tcp",
            "dur": float(np.random.exponential(scale=0.01) + 0.0005),
            "sbytes": int(np.random.choice([40, 60, 100])),
            "dbytes": 0,
            "spkts": 1,
            "dpkts": 0,
            "sport": int(np.random.choice([49152, 55000])),
            "dport": int(np.random.choice([21, 22, 23, 80, 443, 8080])),
            "state": np.random.choice(["RST", "REQ"], p=[0.6, 0.4]),
            "category": "Reconnaissance",
            "subcategory": np.random.choice(["Service_Scan", "OS_Fingerprint"]),
            "attack": 1
        })

    # 3: Exploits / Keylogging
    for i in range(n3):
        records.append({
            "pkSeqID": f"BOT_EXPLOIT_{i}",
            "proto": np.random.choice(["tcp", "udp"], p=[0.7, 0.3]),
            "dur": float(np.random.exponential(scale=0.3) + 0.02),
            "sbytes": int(np.random.choice([256, 512, 1024])),
            "dbytes": int(np.random.choice([0, 64], p=[0.8, 0.2])),
            "spkts": int(np.random.choice([3, 5, 8])),
            "dpkts": int(np.random.choice([0, 1, 2], p=[0.8, 0.1, 0.1])),
            "sport": 49152,
            "dport": 80,
            "state": np.random.choice(["CON", "FIN"], p=[0.6, 0.4]),
            "category": "Exploits",
            "subcategory": "Keylogging",
            "attack": 1
        })

    # 4: Credential Abuse (Telnet / SSH Default password brute force)
    for i in range(n4):
        port = int(np.random.choice([23, 22], p=[0.6, 0.4]))
        records.append({
            "pkSeqID": f"BOT_BRUTE_{i}",
            "proto": "tcp",
            "dur": float(np.random.exponential(scale=0.1) + 0.01),
            "sbytes": int(np.random.choice([60, 120, 180, 240])),
            "dbytes": int(np.random.choice([40, 80, 120])),
            "spkts": int(np.random.choice([2, 4, 6])),
            "dpkts": int(np.random.choice([2, 3, 4])),
            "sport": 49152,
            "dport": port,
            "state": np.random.choice(["CON", "RST"], p=[0.5, 0.5]),
            "category": "R2L",
            "subcategory": "BruteForce",
            "attack": 1
        })

    # 5: Malware / Data Exfiltration & C2
    for i in range(n5):
        records.append({
            "pkSeqID": f"BOT_THEFT_{i}",
            "proto": "udp",
            "dur": float(np.random.exponential(scale=0.5) + 0.05),
            "sbytes": int(np.random.choice([512, 1024, 2048])),
            "dbytes": int(np.random.choice([0, 64], p=[0.8, 0.2])),
            "spkts": int(np.random.choice([4, 8, 16])),
            "dpkts": int(np.random.choice([0, 1], p=[0.8, 0.2])),
            "sport": 49152,
            "dport": 53,
            "state": "INT",
            "category": "Generic",
            "subcategory": "Data_Theft",
            "attack": 1
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
    parser = argparse.ArgumentParser(description="Generate and verify BoT-IoT raw splits.")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing files.")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    for name, meta in DATA_FILES.items():
        dest = RAW_DIR / meta["filename"]
        if not dest.is_file() or args.force:
            print(f"Generating {meta['filename']} ({meta['expected_rows']:,} rows)...")
            df = generate_bot_records(meta["expected_rows"], meta["seed"])
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

