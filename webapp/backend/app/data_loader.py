"""
Data Loader and Analytics Service for Multi-Dataset Webapp
Supports NSL-KDD, UNSW-NB15, Common Harmonized Dataset, and Models Benchmark.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PIPELINE = PROJECT_ROOT / "data-pipeline"
MODEL_DIR = PROJECT_ROOT / "model"

class DataStore:
    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get_dataset_metadata(self) -> Dict[str, Any]:
        return {
            "datasets": [
                {
                    "id": "common",
                    "name": "Common (Harmonized Merged)",
                    "description": "Cross-dataset merged table of NSL-KDD and UNSW-NB15",
                    "available_splits": ["all", "train", "validation", "test"]
                },
                {
                    "id": "nsl-kdd",
                    "name": "NSL-KDD",
                    "description": "Benchmark network intrusion detection dataset (Train, Test+, Test-21)",
                    "available_splits": ["all", "train", "test", "test-21"]
                },
                {
                    "id": "unsw-nb15",
                    "name": "UNSW-NB15",
                    "description": "Modern synthetic and real normal traffic network dataset",
                    "available_splits": ["all", "train", "test"]
                }
            ]
        }

    def get_eda_summary(self, dataset_id: str = "common", split: str = "all") -> Dict[str, Any]:
        cache_key = f"eda_{dataset_id}_{split.lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        data = self._compute_eda(dataset_id, split)
        self._cache[cache_key] = data
        return data

    def _compute_eda(self, dataset_id: str, split: str) -> Dict[str, Any]:
        split_lower = split.lower()
        if dataset_id == "common":
            feat_path = DATA_PIPELINE / "common" / "output" / "harmonized" / "features.csv"
            lbl_path = DATA_PIPELINE / "common" / "output" / "harmonized" / "labels.csv"
            meta_path = DATA_PIPELINE / "common" / "output" / "harmonized" / "metadata.csv"

            if not (feat_path.exists() and lbl_path.exists()):
                return {"error": "Common harmonized dataset files not found"}

            # Load 100% full dataset with selective columns for fast execution
            df_lbl = pd.read_csv(lbl_path, usecols=["label_binary", "attack_category"])
            df_feat = pd.read_csv(feat_path, usecols=["protocol", "duration", "bytes_forward"])
            df_meta = pd.read_csv(meta_path, usecols=["data_split", "source_split"]) if meta_path.exists() else pd.DataFrame()

            if split_lower != "all" and not df_meta.empty:
                if split_lower in ["train", "validation", "test"]:
                    mask = df_meta["data_split"].str.lower() == split_lower
                else:
                    mask = df_meta["source_split"].str.lower() == split_lower
                df_lbl = df_lbl[mask]
                df_feat = df_feat[mask]

        elif dataset_id == "nsl-kdd":
            feat_path = DATA_PIPELINE / "NSL-KDD" / "output" / "harmonized" / "features.csv"
            lbl_path = DATA_PIPELINE / "NSL-KDD" / "output" / "harmonized" / "labels.csv"
            meta_path = DATA_PIPELINE / "NSL-KDD" / "output" / "harmonized" / "metadata.csv"

            if not (feat_path.exists() and lbl_path.exists()):
                return {"error": "NSL-KDD harmonized dataset files not found"}

            # Load 100% full dataset
            df_lbl = pd.read_csv(lbl_path, usecols=["label_binary", "attack_category"])
            df_feat = pd.read_csv(feat_path, usecols=["protocol", "duration", "bytes_forward"])
            df_meta = pd.read_csv(meta_path, usecols=["source_split", "is_kddtest21_view"]) if meta_path.exists() else pd.DataFrame()

            if split_lower != "all" and not df_meta.empty:
                if split_lower in ["test-21", "kddtest21", "test21"]:
                    mask = df_meta["is_kddtest21_view"] == True
                elif split_lower in ["train", "kddtrain"]:
                    mask = df_meta["source_split"].str.lower() == "train"
                elif split_lower in ["test", "kddtest"]:
                    mask = df_meta["source_split"].str.lower() == "test"
                else:
                    mask = df_meta["source_split"].str.lower() == split_lower
                df_lbl = df_lbl[mask]
                df_feat = df_feat[mask]

        else: # unsw-nb15
            feat_path = DATA_PIPELINE / "UNSW-NB15" / "output" / "harmonized" / "features.csv"
            lbl_path = DATA_PIPELINE / "UNSW-NB15" / "output" / "harmonized" / "labels.csv"
            meta_path = DATA_PIPELINE / "UNSW-NB15" / "output" / "harmonized" / "metadata.csv"

            if not (feat_path.exists() and lbl_path.exists()):
                return {"error": "UNSW-NB15 harmonized dataset files not found"}

            # Load 100% full dataset
            df_lbl = pd.read_csv(lbl_path, usecols=["label_binary", "attack_category"])
            df_feat = pd.read_csv(feat_path, usecols=["protocol", "duration", "bytes_forward"])
            df_meta = pd.read_csv(meta_path, usecols=["source_split"]) if meta_path.exists() else pd.DataFrame()

            if split_lower != "all" and not df_meta.empty:
                if split_lower in ["train", "training"]:
                    mask = df_meta["source_split"].str.lower() == "train"
                elif split_lower in ["test", "testing"]:
                    mask = df_meta["source_split"].str.lower() == "test"
                else:
                    mask = df_meta["source_split"].str.lower() == split_lower
                df_lbl = df_lbl[mask]
                df_feat = df_feat[mask]

        # Binary distribution across 100% of dataset
        binary_counts = df_lbl["label_binary"].value_counts().to_dict()
        binary_dist = [
            {"label": "Normal" if int(k) == 0 else "Attack", "count": int(v)}
            for k, v in sorted(binary_counts.items())
        ]

        # Category distribution across 100% of dataset
        cat_counts = df_lbl["attack_category"].value_counts().head(10).to_dict() if "attack_category" in df_lbl.columns else {}
        cat_dist = [{"category": str(k), "count": int(v)} for k, v in cat_counts.items()]

        # Protocol distribution across 100% of dataset
        proto_counts = df_feat["protocol"].value_counts().head(10).to_dict() if "protocol" in df_feat.columns else {}
        proto_dist = [{"protocol": str(k), "count": int(v)} for k, v in proto_counts.items()]

        # Uniform sample for scatter plot (downsampled to 1,000 points for browser rendering performance)
        sample_records = []
        if "duration" in df_feat.columns and "bytes_forward" in df_feat.columns:
            sub = pd.concat([
                df_feat[["duration", "bytes_forward"]],
                df_lbl[["label_binary"]]
            ], axis=1).dropna()
            if len(sub) > 1000:
                sub = sub.sample(n=1000, random_state=42)
            for _, r in sub.iterrows():
                sample_records.append({
                    "duration": float(r["duration"]),
                    "bytes_forward": float(r["bytes_forward"]),
                    "is_attack": int(r["label_binary"])
                })

        total_records = len(df_lbl)
        attack_share = float(df_lbl["label_binary"].mean()) if total_records > 0 else 0.0

        return {
            "dataset_id": dataset_id,
            "split": split,
            "total_rows": total_records,
            "total_rows_sampled": total_records,
            "is_full_dataset": True,
            "attack_ratio": attack_share,
            "binary_distribution": binary_dist,
            "category_distribution": cat_dist,
            "protocol_distribution": proto_dist,
            "scatter_sample": sample_records,
            "scatter_sample_size": len(sample_records),
            "scatter_note": "Rendered 1,000 sample points uniformly for visual clarity; all metric totals and class distributions reflect 100% of the dataset."
        }

    def get_cleansing_report(self, dataset_id: str = "common") -> Dict[str, Any]:
        if dataset_id == "unsw-nb15":
            audit_file = DATA_PIPELINE / "UNSW-NB15" / "output" / "cleansing" / "cleansing_audit.csv"
            manifest_file = DATA_PIPELINE / "UNSW-NB15" / "output" / "cleansing" / "source_manifest.csv"
            audit_rows = []
            manifest_rows = []
            if audit_file.exists():
                audit_rows = pd.read_csv(audit_file).to_dict(orient="records")
            if manifest_file.exists():
                manifest_rows = pd.read_csv(manifest_file).to_dict(orient="records")
            return {
                "dataset": "UNSW-NB15",
                "audit": audit_rows,
                "manifest": manifest_rows,
                "quality_summary": {
                    "missing_values_handled": "Imputed empty service/state with 'other'",
                    "outliers_policy": "Retained with validity flags",
                    "duplicate_handling": "Flagged without discarding"
                }
            }
        elif dataset_id == "nsl-kdd":
            audit_file = DATA_PIPELINE / "NSL-KDD" / "output" / "clean" / "cleaning_report.csv"
            if not audit_file.exists():
                audit_file = DATA_PIPELINE / "output" / "NSL-KDD" / "cleaning_report.csv"
            audit_rows = []
            if audit_file.exists():
                audit_rows = pd.read_csv(audit_file).to_dict(orient="records")
            return {
                "dataset": "NSL-KDD",
                "audit": audit_rows,
                "quality_summary": {
                    "missing_values": "0 missing values across standard splits",
                    "attack_families": "Mapped 39 attack types to 4 categories (DoS, Probe, R2L, U2R)",
                    "difficulty_level": "Preserved for subset analysis (KDDTest-21)"
                }
            }
        else:
            rep_file = DATA_PIPELINE / "common" / "output" / "reports" / "build_summary.csv"
            rep_rows = []
            if rep_file.exists():
                rep_rows = pd.read_csv(rep_file).to_dict(orient="records")
            return {
                "dataset": "Common Harmonized",
                "build_report": rep_rows,
                "quality_summary": {
                    "schema_alignment": "Verified duration, protocol, bytes_forward, bytes_backward",
                    "record_separation": "Strict split between model features, labels, and metadata",
                    "leakage_prevention": "Record IDs and source labels excluded from training features"
                }
            }

    def get_feature_contract(self) -> Dict[str, Any]:
        contract_file = DATA_PIPELINE / "common" / "feature_contract.json"
        schema_file = DATA_PIPELINE / "common" / "output" / "feature_engineering" / "feature_schema.json"
        contract = {}
        schema = {}
        if contract_file.exists():
            with open(contract_file, "r", encoding="utf-8") as f:
                contract = json.load(f)
        if schema_file.exists():
            with open(schema_file, "r", encoding="utf-8") as f:
                schema = json.load(f)
        return {
            "contract": contract,
            "feature_schema": schema
        }

    def get_all_model_runs(self) -> List[Dict[str, Any]]:
        runs = []

        # 1. XGBoost
        xgb_backup = MODEL_DIR / "xgboost" / "backup"
        if xgb_backup.exists():
            for entry in sorted(xgb_backup.iterdir(), reverse=True):
                if not entry.is_dir():
                    continue
                eval_file = entry / "evaluation_results.json"
                if not eval_file.exists():
                    eval_file = entry / "metrics.json"
                if eval_file.exists():
                    try:
                        with open(eval_file, "r", encoding="utf-8") as f:
                            d = json.load(f)
                        km = d.get("kddtest_metrics", {})
                        km21 = d.get("kddtest21_metrics", {})
                        mode = d.get("mode", "binary")
                        runs.append({
                            "id": f"xgboost::{entry.name}",
                            "family": "XGBoost",
                            "model_name": d.get("model_name", "XGBoost"),
                            "run_id": entry.name,
                            "mode": mode,
                            "timestamp": d.get("timestamp", entry.name),
                            "kddtest": {
                                "accuracy": km.get("accuracy"),
                                "balanced_accuracy": km.get("balanced_accuracy"),
                                "f1": km.get("macro_f1") or km.get("f1"),
                                "precision": km.get("precision"),
                                "recall": km.get("recall"),
                                "false_positive_rate": km.get("false_positive_rate"),
                                "confusion_matrix": d.get("confusion_matrix_kddtest", []),
                                "classes": d.get("classes", ["Normal", "Attack"])
                            },
                            "kddtest21": {
                                "accuracy": km21.get("accuracy"),
                                "balanced_accuracy": km21.get("balanced_accuracy"),
                                "f1": km21.get("macro_f1") or km21.get("f1"),
                                "precision": km21.get("precision"),
                                "recall": km21.get("recall"),
                                "confusion_matrix": d.get("confusion_matrix_kddtest21", [])
                            },
                            "hyperparameters": d.get("hyperparameters", {})
                        })
                    except Exception:
                        pass

        # 2. MLP
        mlp_dirs = [
            MODEL_DIR / "mlp" / "backup",
            MODEL_DIR / "mlp" / "Backup",
            MODEL_DIR / "mlp" / "Backup" / "runs",
            DATA_PIPELINE / "NSL-KDD" / "output" / "model_runs" / "mlp"
        ]
        seen_mlp = set()
        for mdir in mlp_dirs:
            if not mdir.exists():
                continue
            subdirs = [mdir] if mdir.name == "mlp" else [e for e in sorted(mdir.iterdir(), reverse=True) if e.is_dir() and e.name != "runs"]
            for sdir in subdirs:
                # Check for metrics.json (modern standardized format)
                mf = sdir / "metrics.json"
                if mf.exists() and sdir.name not in seen_mlp:
                    seen_mlp.add(sdir.name)
                    try:
                        with open(mf, "r", encoding="utf-8") as f:
                            d = json.load(f)
                        km = d.get("kddtest_metrics", {})
                        km21 = d.get("kddtest21_metrics", {})
                        runs.append({
                            "id": f"mlp::{sdir.name}",
                            "family": "MLP",
                            "model_name": d.get("model_name", f"MLP ({sdir.name})"),
                            "run_id": sdir.name,
                            "mode": d.get("mode", "binary"),
                            "timestamp": d.get("timestamp", sdir.name),
                            "kddtest": {
                                "accuracy": km.get("accuracy"),
                                "balanced_accuracy": km.get("balanced_accuracy"),
                                "f1": km.get("macro_f1") or km.get("f1"),
                                "precision": km.get("precision"),
                                "recall": km.get("recall"),
                                "false_positive_rate": km.get("false_positive_rate"),
                                "confusion_matrix": d.get("confusion_matrix_kddtest", []),
                                "classes": d.get("classes", ["Normal", "Attack"])
                            },
                            "kddtest21": {
                                "accuracy": km21.get("accuracy"),
                                "balanced_accuracy": km21.get("balanced_accuracy"),
                                "f1": km21.get("macro_f1") or km21.get("f1"),
                                "precision": km21.get("precision"),
                                "recall": km21.get("recall"),
                                "confusion_matrix": d.get("confusion_matrix_kddtest21", [])
                            },
                            "hyperparameters": d.get("hyperparameters", {})
                        })
                        continue
                    except Exception:
                        pass

                # Check for results_*.json (legacy format)
                for rf in sorted(sdir.glob("results_*.json")):
                    try:
                        with open(rf, "r", encoding="utf-8") as f:
                            d = json.load(f)
                        task = d.get("task", "binary")
                        run_key = f"{sdir.name}::{task}"
                        if run_key in seen_mlp:
                            continue
                        seen_mlp.add(run_key)
                        tp = d.get("kdd_test_plus", {})
                        t21 = d.get("kdd_test_21", {})
                        meta = d.get("run_metadata", {})
                        runs.append({
                            "id": f"mlp::{sdir.name}::{task}",
                            "family": "MLP",
                            "model_name": f"MLP ({task.capitalize()})",
                            "run_id": f"{sdir.name} ({task})",
                            "mode": task,
                            "timestamp": meta.get("started_at", sdir.name),
                            "kddtest": {
                                "accuracy": tp.get("accuracy"),
                                "balanced_accuracy": tp.get("balanced_accuracy"),
                                "f1": tp.get("macro_f1"),
                                "precision": tp.get("macro_precision"),
                                "recall": tp.get("macro_recall"),
                                "confusion_matrix": tp.get("confusion_matrix", []),
                                "classes": d.get("class_names", ["Normal", "Attack"])
                            },
                            "kddtest21": {
                                "accuracy": t21.get("accuracy"),
                                "balanced_accuracy": t21.get("balanced_accuracy"),
                                "f1": t21.get("macro_f1"),
                                "precision": t21.get("macro_precision"),
                                "recall": t21.get("macro_recall"),
                                "confusion_matrix": t21.get("confusion_matrix", [])
                            },
                            "hyperparameters": {
                                "epochs": d.get("epochs"),
                                "batch_size": d.get("batch_size"),
                                "learning_rate": d.get("learning_rate"),
                                "seed": d.get("seed")
                            }
                        })
                    except Exception:
                        pass

        # 3. Autoencoder
        ae_dir = MODEL_DIR / "autoencoder" / "backup"
        if ae_dir.exists():
            for entry in sorted(ae_dir.iterdir(), reverse=True):
                if not entry.is_dir():
                    continue
                mf = entry / "metrics.json"
                if mf.exists():
                    try:
                        with open(mf, "r", encoding="utf-8") as f:
                            m = json.load(f)
                        cf = entry / "config.json"
                        cdata = {}
                        if cf.exists():
                            with open(cf, "r", encoding="utf-8") as cff:
                                cdata = json.load(cff)
                        cm_file = entry / "confusion_matrix.json"
                        cm = m.get("confusion_matrix_kddtest") or m.get("kddtest_metrics", {}).get("confusion_matrix")
                        if not cm:
                            cm = [[m.get("tn", 0), m.get("fp", 0)], [m.get("fn", 0), m.get("tp", 0)]]
                            if cm_file.exists():
                                with open(cm_file, "r", encoding="utf-8") as cmf:
                                    cm = json.load(cmf).get("matrix", cm)
                        
                        km = m.get("kddtest_metrics", {})
                        km21 = m.get("kddtest21_metrics", {})
                        acc = km.get("accuracy") if km.get("accuracy") is not None else m.get("accuracy")
                        rec = km.get("recall") if km.get("recall") is not None else m.get("recall", 0)
                        fpr = km.get("false_positive_rate") if km.get("false_positive_rate") is not None else m.get("false_positive_rate", 0)
                        f1_val = km.get("f1") if km.get("f1") is not None else m.get("f1")
                        prec = km.get("precision") if km.get("precision") is not None else m.get("precision")

                        runs.append({
                            "id": f"autoencoder::{entry.name}",
                            "family": "Autoencoder",
                            "model_name": m.get("model_name", "Autoencoder Anomaly"),
                            "run_id": entry.name,
                            "mode": "binary",
                            "timestamp": m.get("timestamp", entry.name),
                            "kddtest": {
                                "accuracy": acc,
                                "balanced_accuracy": 0.5 * ((rec or 0) + (1.0 - (fpr or 0))),
                                "f1": f1_val,
                                "precision": prec,
                                "recall": rec,
                                "false_positive_rate": fpr,
                                "confusion_matrix": cm,
                                "classes": ["Normal", "Attack"]
                            },
                            "kddtest21": {
                                "accuracy": km21.get("accuracy"),
                                "f1": km21.get("f1"),
                                "recall": km21.get("recall")
                            },
                            "hyperparameters": m.get("hyperparameters", {
                                "threshold_percentile": m.get("threshold_percentile", cdata.get("threshold_percentile", 95.0)),
                                "epochs": cdata.get("epochs", 20),
                                "batch_size": cdata.get("batch_size", 256),
                                "learning_rate": cdata.get("learning_rate", 0.001)
                            })
                        })
                    except Exception:
                        pass

        # 4. Isolation Forest
        iso_dir = MODEL_DIR / "isolation-forest" / "backup"
        seen_iso = set()
        if iso_dir.exists():
            for entry in sorted(iso_dir.iterdir(), reverse=True):
                if not entry.is_dir():
                    continue
                mf = entry / "metrics.json"
                if mf.exists():
                    seen_iso.add(entry.name)
                    try:
                        with open(mf, "r", encoding="utf-8") as f:
                            m = json.load(f)
                        km = m.get("kddtest_metrics", {})
                        km21 = m.get("kddtest21_metrics", {})
                        runs.append({
                            "id": f"isolation_forest::{entry.name}",
                            "family": "Isolation Forest",
                            "model_name": m.get("model_name", f"Isolation Forest ({entry.name})"),
                            "run_id": entry.name,
                            "mode": "binary",
                            "timestamp": m.get("timestamp", entry.name),
                            "kddtest": {
                                "accuracy": km.get("accuracy"),
                                "balanced_accuracy": km.get("balanced_accuracy"),
                                "f1": km.get("f1"),
                                "precision": km.get("precision"),
                                "recall": km.get("recall"),
                                "false_positive_rate": km.get("false_positive_rate"),
                                "confusion_matrix": m.get("confusion_matrix_kddtest", []),
                                "classes": ["Normal", "Attack"]
                            },
                            "kddtest21": {
                                "accuracy": km21.get("accuracy"),
                                "f1": km21.get("f1"),
                                "recall": km21.get("recall"),
                                "confusion_matrix": m.get("confusion_matrix_kddtest21", [])
                            },
                            "hyperparameters": m.get("hyperparameters", {})
                        })
                    except Exception:
                        pass

        iso_csv = DATA_PIPELINE / "output" / "NSL-KDD" / "isolation_forest" / "evaluation_metrics.csv"
        if not iso_csv.exists():
            iso_csv = DATA_PIPELINE / "NSL-KDD" / "output" / "model_runs" / "isolation_forest_single" / "evaluation_metrics.csv"
        if iso_csv.exists():
            try:
                idf = pd.read_csv(iso_csv)
                krow = idf[idf["dataset"] == "KDDTest"].iloc[0].to_dict() if len(idf[idf["dataset"] == "KDDTest"]) > 0 else {}
                k21row = idf[idf["dataset"] == "KDDTest-21"].iloc[0].to_dict() if len(idf[idf["dataset"] == "KDDTest-21"]) > 0 else {}

                def parse_cm(row):
                    tn = row.get("true_negative", 0)
                    fp = row.get("false_positive", 0)
                    fn = row.get("false_negative", 0)
                    tp = row.get("true_positive", 0)
                    tot = tn + fp + fn + tp
                    acc = (tp + tn) / tot if tot > 0 else 0.0
                    return acc, [[tn, fp], [fn, tp]]

                k_acc, k_cm = parse_cm(krow)
                k21_acc, k21_cm = parse_cm(k21row)

                runs.append({
                    "id": "isolation_forest::default",
                    "family": "Isolation Forest",
                    "model_name": "Isolation Forest",
                    "run_id": "Quantile-Alert-Fit",
                    "mode": "binary",
                    "timestamp": "Baseline",
                    "kddtest": {
                        "accuracy": k_acc,
                        "balanced_accuracy": 0.5 * (krow.get("recall_at_threshold", 0) + (1.0 - krow.get("false_positive_rate", 0))),
                        "f1": krow.get("f1_at_threshold"),
                        "precision": krow.get("precision_at_threshold"),
                        "recall": krow.get("recall_at_threshold"),
                        "false_positive_rate": krow.get("false_positive_rate"),
                        "confusion_matrix": k_cm,
                        "classes": ["Normal", "Attack"]
                    },
                    "kddtest21": {
                        "accuracy": k21_acc,
                        "balanced_accuracy": 0.5 * (k21row.get("recall_at_threshold", 0) + (1.0 - k21row.get("false_positive_rate", 0))),
                        "f1": k21row.get("f1_at_threshold"),
                        "precision": k21row.get("precision_at_threshold"),
                        "recall": k21row.get("recall_at_threshold"),
                        "confusion_matrix": k21_cm
                    },
                    "hyperparameters": {
                        "n_estimators": 50,
                        "alert_rate": 0.05,
                        "threshold_anomaly_score": krow.get("threshold_anomaly_score")
                    }
                })
            except Exception:
                pass

        return runs

    def delete_model_run(self, model_id: str) -> bool:
        """Deletes a model run directory from disk by run id or compound id."""
        import shutil
        deleted = False

        # Parts parsing: e.g. "xgboost::xgboost-common-2026-..." or just the run name
        if "::" in model_id:
            fam_key, run_name = model_id.split("::", 1)
        else:
            fam_key, run_name = "", model_id

        # Normalize family names
        fam_candidates = []
        if fam_key:
            fk = fam_key.lower().replace("_", "-")
            fam_candidates = [fk, fk.replace("-", "_"), fk.replace("-", "")]
        else:
            fam_candidates = ["xgboost", "mlp", "autoencoder", "isolation-forest"]

        for fc in fam_candidates:
            for bname in ["backup", "Backup"]:
                bdir = MODEL_DIR / fc / bname
                if bdir.exists():
                    target = bdir / run_name
                    if target.exists() and target.is_dir():
                        shutil.rmtree(target)
                        deleted = True

        # Clear memory cache so /api/models reflects deletion immediately
        self._cache.clear()
        return deleted

store = DataStore()

