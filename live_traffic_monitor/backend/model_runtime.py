#!/usr/bin/env python3
"""Two-Stage Production XGBoost Model Runtime for Live Traffic Monitor.

Loads M9 Production Models:
- Stage 1: production_xgb_binary.json (High-speed binary filter with threshold 0.45)
- Stage 2: production_xgb_multiclass.json (6-class MITRE ATT&CK classifier)
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import xgboost as xgb

BASE_DIR = Path(__file__).resolve().parent.parent
EXP_PROD_DIR = BASE_DIR.parent / "experiments" / "scaling_and_domain_shift" / "models" / "production"

CLASS_NAMES = [
    "Benign / Normal",
    "Denial of Service (DoS)",
    "Reconnaissance & Probing",
    "Exploits & PrivEsc",
    "Credential Abuse (R2L)",
    "Malware, C2 & Botnet",
]

TACTICS = [
    "Normal Traffic",
    "Impact (T0814)",
    "Discovery (T1046)",
    "Initial Access & Execution (T1190)",
    "Credential Access (T1110)",
    "Command and Control (T1071)",
]

MITRE_DESCRIPTIONS = [
    "Normal authorized business traffic.",
    "High-volume resource exhaustion flooding service availability.",
    "Network discovery, port scanning, and service version enumeration.",
    "Remote code execution, SQL injection, vulnerability exploitation.",
    "Password guessing, dictionary attack, and credential abuse.",
    "Botnet command-and-control beaconing, Trojan or Worm activity.",
]


class ModelRuntime:
    def __init__(self, models_dir: Path = EXP_PROD_DIR):
        self.models_dir = Path(models_dir)
        self.bin_model_path = self.models_dir / "production_xgb_binary.json"
        self.multi_model_path = self.models_dir / "production_xgb_multiclass.json"
        self.threshold_path = self.models_dir / "threshold_config.json"
        self.contract_path = self.models_dir / "feature_contract.json"

        # Defaults
        self.optimal_threshold = 0.45
        self.feature_columns = [
            "dur", "sbytes", "dbytes", "proto_icmp", "proto_other", "proto_tcp", "proto_udp",
            "srv_dns", "srv_ftp", "srv_http", "srv_https_ssl", "srv_other", "srv_smtp", "srv_ssh",
            "st_established", "st_no-reply", "st_other", "st_reset", "flow_byte_rate"
        ]

        self._load_models()

    def _load_models(self):
        if self.threshold_path.exists():
            with open(self.threshold_path) as f:
                th_data = json.load(f)
                self.optimal_threshold = th_data.get("optimal_threshold", 0.45)

        if self.contract_path.exists():
            with open(self.contract_path) as f:
                contract = json.load(f)
                self.feature_columns = [col for col in contract.get("features", []) if col != "record_id"]

        print(f"Loading Stage 1 Binary Model from {self.bin_model_path}...")
        self.clf_bin = xgb.XGBClassifier()
        self.clf_bin.load_model(str(self.bin_model_path))

        print(f"Loading Stage 2 Multiclass Model from {self.multi_model_path}...")
        self.clf_multi = xgb.XGBClassifier()
        self.clf_multi.load_model(str(self.multi_model_path))
        print("Production Two-Stage Models loaded successfully!")

    def predict_single(self, features_dict: Dict[str, float]) -> Dict[str, Any]:
        """Runs two-stage inference on a single flow features dict."""
        t0 = time.perf_counter()

        # Construct vector in exact contract order
        vec = [float(features_dict.get(col, 0.0)) for col in self.feature_columns]
        X = pd.DataFrame([vec], columns=self.feature_columns)

        # Stage 1: Binary Model
        prob_attack = float(self.clf_bin.predict_proba(X)[0, 1])
        is_attack = bool(prob_attack >= self.optimal_threshold)

        if not is_attack:
            predicted_class = 0
            class_name = CLASS_NAMES[0]
            confidence = round((1.0 - prob_attack) * 100, 2)
            tactic = TACTICS[0]
            severity = "info"
        else:
            # Stage 2: Multiclass Model (only if Stage 1 flagged attack)
            probs_multi = self.clf_multi.predict_proba(X)[0]
            # Classes 1 to 5
            predicted_class = int(np.argmax(probs_multi))
            if predicted_class == 0:
                # If multiclass predicted normal but binary flagged attack, choose top attack class
                attack_probs = probs_multi[1:]
                predicted_class = int(np.argmax(attack_probs) + 1)

            class_name = CLASS_NAMES[predicted_class]
            confidence = round(float(probs_multi[predicted_class]) * 100, 2)
            tactic = TACTICS[predicted_class]
            severity = "critical" if predicted_class in [1, 3, 5] else "warning"

        latency_ms = round((time.perf_counter() - t0) * 1000, 3)

        return {
            "is_attack": is_attack,
            "binary_score": round(prob_attack, 4),
            "threshold": self.optimal_threshold,
            "predicted_class_id": predicted_class,
            "predicted_class_name": class_name,
            "confidence": confidence,
            "tactic": tactic,
            "description": MITRE_DESCRIPTIONS[predicted_class],
            "severity": severity,
            "inference_latency_ms": latency_ms,
        }

    def predict_batch(self, df_features: pd.DataFrame) -> List[Dict[str, Any]]:
        """Runs vectorized two-stage inference on an entire batch of flows."""
        t0 = time.perf_counter()
        X = df_features[self.feature_columns]
        probs_bin = self.clf_bin.predict_proba(X)[:, 1]
        is_attacks = probs_bin >= self.optimal_threshold

        # Multi-class inference
        probs_multi = self.clf_multi.predict_proba(X)

        total_lat = (time.perf_counter() - t0) * 1000
        lat_per_flow = round(total_lat / max(1, len(X)), 3)

        results = []
        for i in range(len(X)):
            prob_att = float(probs_bin[i])
            is_att = bool(is_attacks[i])

            if not is_att:
                predicted_class = 0
                class_name = CLASS_NAMES[0]
                confidence = round((1.0 - prob_att) * 100, 2)
                tactic = TACTICS[0]
                severity = "info"
            else:
                p_multi = probs_multi[i]
                predicted_class = int(np.argmax(p_multi))
                if predicted_class == 0:
                    predicted_class = int(np.argmax(p_multi[1:]) + 1)
                class_name = CLASS_NAMES[predicted_class]
                confidence = round(float(p_multi[predicted_class]) * 100, 2)
                tactic = TACTICS[predicted_class]
                severity = "critical" if predicted_class in [1, 3, 5] else "warning"

            results.append(
                {
                    "is_attack": is_att,
                    "binary_score": round(prob_att, 4),
                    "threshold": self.optimal_threshold,
                    "predicted_class_id": predicted_class,
                    "predicted_class_name": class_name,
                    "confidence": confidence,
                    "tactic": tactic,
                    "description": MITRE_DESCRIPTIONS[predicted_class],
                    "severity": severity,
                    "inference_latency_ms": lat_per_flow,
                }
            )

        return results


if __name__ == "__main__":
    runtime = ModelRuntime()
    dummy_feat = {col: 0.0 for col in runtime.feature_columns}
    dummy_feat["sbytes"] = 1500
    dummy_feat["dbytes"] = 4500
    dummy_feat["srv_http"] = 1.0
    dummy_feat["st_established"] = 1.0
    res = runtime.predict_single(dummy_feat)
    print("Test inference result:")
    print(json.dumps(res, indent=2))
