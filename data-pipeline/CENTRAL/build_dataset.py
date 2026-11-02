#!/usr/bin/env python3
"""
Quad-Dataset Central Harmonization Pipeline
Harmonizes NSL-KDD, UNSW-NB15, CIC-IDS2017, and BoT-IoT into CENTRAL/output/harmonized.
Preserves official train/test splits, carving a 20% validation subset from train.
"""

from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CENTRAL_DIR = PROJECT_ROOT / "data-pipeline" / "CENTRAL"
DATASETS = ("NSL-KDD", "UNSW-NB15", "CIC-IDS2017", "BoT-IoT")

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def assign_splits(metadata: pd.DataFrame, seed: int = 42, validation_fraction: float = 0.20) -> pd.Series:
    """Preserves official train/test; carves 20% validation from train using seeded split."""
    result = pd.Series(pd.NA, index=metadata.index, dtype="string")
    for source, indexes in metadata.groupby("source_dataset", sort=True).groups.items():
        block = metadata.loc[indexes]
        official = block["source_split"].astype("string").str.lower()

        # Handle train/test
        train_mask = official.isin(["train", "kddtrain"])
        test_mask = official.isin(["test", "kddtest"])

        train_indices = block.index[train_mask].to_numpy()
        test_indices = block.index[test_mask].to_numpy()

        rng = np.random.default_rng(seed)
        shuffled = rng.permutation(train_indices)
        val_size = int(np.floor(len(shuffled) * validation_fraction))

        val_indices = shuffled[:val_size]
        actual_train_indices = shuffled[val_size:]

        result.loc[actual_train_indices] = "train"
        result.loc[val_indices] = "validation"
        result.loc[test_indices] = "test"

    return result

def main():
    print("=" * 80)
    print("CENTRAL DATASET HARMONIZATION: QUAD BENCHMARK SUITE")
    print("Datasets: NSL-KDD, UNSW-NB15, CIC-IDS2017, BoT-IoT")
    print("=" * 80)

    feature_parts, label_parts, metadata_parts = [], [], []

    for name in DATASETS:
        ds_dir = PROJECT_ROOT / "data-pipeline" / name / "output" / "harmonized"
        print(f"Loading {name} harmonized tables from: {ds_dir} ...")

        f_path = ds_dir / "features.csv"
        l_path = ds_dir / "labels.csv"
        m_path = ds_dir / "metadata.csv"

        if not (f_path.is_file() and l_path.is_file() and m_path.is_file()):
            raise FileNotFoundError(f"Missing harmonized files for dataset: {name}")

        f = pd.read_csv(f_path, low_memory=False)
        l = pd.read_csv(l_path, low_memory=False)
        m = pd.read_csv(m_path, low_memory=False)

        assert len(f) == len(l) == len(m), f"Mismatched rows in {name}: f={len(f)}, l={len(l)}, m={len(m)}"
        print(f"  Loaded {len(f):,} rows for {name}")

        feature_parts.append(f)
        label_parts.append(l)
        metadata_parts.append(m)

    print("\nConcatenating tables...")
    features = pd.concat(feature_parts, ignore_index=True)
    labels = pd.concat(label_parts, ignore_index=True)
    metadata = pd.concat(metadata_parts, ignore_index=True)

    assert features["record_id"].is_unique, "Duplicate record_id detected across datasets!"
    assert (features["record_id"] == labels["record_id"]).all(), "Feature and label record_ids out of alignment!"
    assert (features["record_id"] == metadata["record_id"]).all(), "Feature and metadata record_ids out of alignment!"

    # Canonical 6-Class MITRE ATT&CK Mapping
    mitre_map = {
        "normal": (0, "Benign / Normal", "Baseline Operations"),
        "benign": (0, "Benign / Normal", "Baseline Operations"),
        "dos": (1, "Denial of Service (DoS)", "TA0040: Impact"),
        "dos/ddos": (1, "Denial of Service (DoS)", "TA0040: Impact"),
        "ddos": (1, "Denial of Service (DoS)", "TA0040: Impact"),
        "probe": (2, "Reconnaissance & Probing", "TA0043/TA0007: Recon & Discovery"),
        "probe/recon": (2, "Reconnaissance & Probing", "TA0043/TA0007: Recon & Discovery"),
        "reconnaissance": (2, "Reconnaissance & Probing", "TA0043/TA0007: Recon & Discovery"),
        "analysis": (2, "Reconnaissance & Probing", "TA0043/TA0007: Recon & Discovery"),
        "exploits": (3, "Exploits & PrivEsc", "TA0001/TA0004: Initial Access & PrivEsc"),
        "exploit/u2r": (3, "Exploits & PrivEsc", "TA0001/TA0004: Initial Access & PrivEsc"),
        "shellcode": (3, "Exploits & PrivEsc", "TA0001/TA0004: Initial Access & PrivEsc"),
        "u2r": (3, "Exploits & PrivEsc", "TA0001/TA0004: Initial Access & PrivEsc"),
        "r2l": (4, "Credential Abuse (R2L)", "TA0006: Credential Access"),
        "brute-force/r2l": (4, "Credential Abuse (R2L)", "TA0006: Credential Access"),
        "generic": (5, "Malware, C2 & Botnet", "TA0011/TA0008: C2 & Lateral Movement"),
        "generic/fuzzer": (5, "Malware, C2 & Botnet", "TA0011/TA0008: C2 & Lateral Movement"),
        "fuzzers": (5, "Malware, C2 & Botnet", "TA0011/TA0008: C2 & Lateral Movement"),
        "backdoor": (5, "Malware, C2 & Botnet", "TA0011/TA0008: C2 & Lateral Movement"),
        "botnet/backdoor": (5, "Malware, C2 & Botnet", "TA0011/TA0008: C2 & Lateral Movement"),
        "worms": (5, "Malware, C2 & Botnet", "TA0011/TA0008: C2 & Lateral Movement")
    }

    norm_source = labels["label_source_category"].astype(str).str.strip().str.lower()
    mitre_info = [mitre_map.get(s, (5, "Malware, C2 & Botnet", "TA0011/TA0008: C2 & Lateral Movement")) for s in norm_source]
    labels["attack_category_id"] = [info[0] for info in mitre_info]
    labels["attack_category"] = [info[1] for info in mitre_info]
    labels["mitre_tactic"] = [info[2] for info in mitre_info]
    labels["label_binary"] = (labels["attack_category_id"] > 0).astype(int)

    # Reorder labels columns per feature contract
    labels = labels[["record_id", "label_raw", "label_source_category", "attack_category", "attack_category_id", "label_binary", "mitre_tactic"]]

    print("Assigning stratified train, validation, and test splits (20% val carve)...")
    metadata["data_split"] = assign_splits(metadata, seed=42, validation_fraction=0.20)

    # Calculate balanced sample weights per split
    rows_per_source_split = metadata.groupby(["source_dataset", "data_split"])["record_id"].transform("size")
    metadata["sample_weight"] = 1.0 / rows_per_source_split.astype(float)

    out_harm_dir = CENTRAL_DIR / "output" / "harmonized"
    out_harm_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nWriting central harmonized tables to {out_harm_dir}...")
    features.to_csv(out_harm_dir / "features.csv", index=False)
    labels.to_csv(out_harm_dir / "labels.csv", index=False)
    metadata.to_csv(out_harm_dir / "metadata.csv", index=False)

    report_rows = [
        {"table": "features", "rows": len(features), "columns": len(features.columns)},
        {"table": "labels", "rows": len(labels), "columns": len(labels.columns)},
        {"table": "metadata", "rows": len(metadata), "columns": len(metadata.columns)}
    ]
    pd.DataFrame(report_rows).to_csv(out_harm_dir / "harmonization_report.csv", index=False)

    # Generate split tables
    out_splits_dir = CENTRAL_DIR / "output" / "splits"
    out_splits_dir.mkdir(parents=True, exist_ok=True)

    splits = {
        "train": metadata["data_split"] == "train",
        "validation": metadata["data_split"] == "validation",
        "train_full": metadata["data_split"].isin(["train", "validation"]),
        "test": metadata["data_split"] == "test"
    }

    for split_name, mask in splits.items():
        s_dir = out_splits_dir / split_name
        s_dir.mkdir(parents=True, exist_ok=True)
        print(f"Exporting split '{split_name}' ({mask.sum():,} rows) to {s_dir}...")
        features[mask].to_csv(s_dir / "features.csv", index=False)
        labels[mask].to_csv(s_dir / "labels.csv", index=False)
        metadata[mask].to_csv(s_dir / "metadata.csv", index=False)

    print("\n" + "=" * 80)
    print(f"CENTRAL HARMONIZATION COMPLETE! Total Flows: {len(features):,}")
    print("=" * 80)
    print("Dataset Breakdown:")
    print(metadata["source_dataset"].value_counts())
    print("\nSplit Breakdown:")
    print(pd.crosstab(metadata["source_dataset"], metadata["data_split"], margins=True))

if __name__ == "__main__":
    main()
