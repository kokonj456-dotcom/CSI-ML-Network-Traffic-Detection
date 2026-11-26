"""Load a validated paired model and score normalized flows."""
import hashlib
import json
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from ..models.central_contract import CLASS_NAMES, NAMES, transform_features
from ..config import capture_files
from ..models.flow import CoreFlow


def _digest(stream):
    if hasattr(hashlib, "file_digest"):
        return hashlib.file_digest(stream, "sha256").hexdigest()
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(65536), b""):
        h.update(chunk)
    return h.hexdigest()


class Predictor:
    def __init__(self, directory):
        report = json.loads((directory/"evaluation.json").read_text(encoding="utf-8"))
        self.evaluation = {
            name: {"rows": report[name]["rows"], "binary": report[name]["binary"]}
            for name in ("test_full", "test_feature_group_disjoint")
        }
        self.manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
        feature_names = self.manifest["feature_names"]
        self.feature_names = feature_names
        self.is_uncut = len(feature_names) == 80
        if not self.is_uncut and feature_names != NAMES:
            raise ValueError("Bundle does not match the CENTRAL feature/class contract")
        if self.manifest["class_names"] != CLASS_NAMES:
            raise ValueError("Bundle does not match the CENTRAL feature/class contract")
        if not 0 <= self.manifest["threshold"] <= 1:
            raise ValueError("Threshold is outside [0, 1]")
        for filename in ("binary.json", "multiclass.json", "preprocessor.joblib"):
            with (directory/filename).open("rb") as stream:
                actual = _digest(stream)
            if actual != self.manifest["files"][filename]:
                raise ValueError(f"Fingerprint mismatch: {filename}")
        self.prep = joblib.load(directory/"preprocessor.joblib")
        for key in ("fit_record_ids_sha256", "schema_version"):
            if self.prep[key] != self.manifest[key]:
                raise ValueError(f"Preprocessor does not match manifest: {key}")
        if self.prep["model_feature_names"] != feature_names:
            raise ValueError("Preprocessor has incorrect feature columns")
        self.binary = xgb.XGBClassifier(n_jobs=2)
        self.multi = xgb.XGBClassifier(n_jobs=2)
        self.binary.load_model(directory/"binary.json")
        self.multi.load_model(directory/"multiclass.json")
        for model, count in ((self.binary, 2), (self.multi, 6)):
            if model.get_booster().feature_names != feature_names or list(model.classes_) != list(range(count)):
                raise ValueError("Model has incorrect feature columns or class IDs")

    def metadata(self):
        return {key: self.manifest[key] for key in ("model_id", "threshold", "class_names", "feature_names", "schema_version", "scope")} | {
            "preprocessor_sha256": self.manifest["files"]["preprocessor.joblib"],
            "captures": capture_files(), "evaluation": self.evaluation,
        }

    def predict(self, inputs, *, explain=False):
        output = []
        valid = []
        for index, row in enumerate(inputs):
            try:
                item = CoreFlow.model_validate(row).model_dump()
                valid.append((index, item))
                output.append(None)
            except ValueError:
                output.append({"status":"not_scored", "reason":"Missing or invalid CENTRAL inputs", "model_id":self.manifest["model_id"]})
        if not valid:
            return output
        start = perf_counter()
        if self.is_uncut:
            is_imputed = "imputed" in self.manifest.get("candidate", "").lower()
            fill_val = -1.0 if is_imputed else np.nan
            cat_missing = "missing" if is_imputed else None
            rows_80 = []
            for _, item in valid:
                r = {f: fill_val for f in self.feature_names}
                r["duration"] = float(item["duration"])
                r["bytes_forward"] = float(item["bytes_forward"])
                r["bytes_backward"] = float(item["bytes_backward"])
                r["protocol"] = str(item["protocol"])
                r["service_group"] = str(item["service_group"])
                r["conn_state_group"] = str(item["conn_state_group"])
                r["cic_flow_state"] = cat_missing
                rows_80.append(r)
            features = pd.DataFrame(rows_80)[self.feature_names]
            cat_dtypes = {
                "protocol": pd.CategoricalDtype(categories=["tcp", "udp", "icmp", "other", "missing"]),
                "service_group": pd.CategoricalDtype(categories=["dns", "ftp", "http", "https_ssl", "smtp", "ssh", "other", "missing"]),
                "conn_state_group": pd.CategoricalDtype(categories=["established", "no-reply", "reset", "other", "missing"]),
                "cic_flow_state": pd.CategoricalDtype(categories=["established", "no-reply", "missing"]),
            }
            for col, dt in cat_dtypes.items():
                features[col] = features[col].astype(dt)
            for col in features.columns:
                if col not in cat_dtypes:
                    features[col] = features[col].astype(float)
        else:
            raw = pd.DataFrame([item for _, item in valid]).assign(record_id=[str(i) for i, _ in valid])
            features = transform_features(raw, self.prep)[NAMES]
        attack_scores = self.binary.predict_proba(features)[:, 1]
        category_probabilities = self.multi.predict_proba(features)
        latency = (perf_counter() - start) * 1000 / len(valid)
        contributions = None
        if explain:
            contributions = self.binary.get_booster().predict(xgb.DMatrix(features), pred_contribs=True)
        threshold = self.manifest["threshold"]

        for row, (index, item) in enumerate(valid):
            score = float(attack_scores[row])
            flagged = score >= threshold
            probabilities = category_probabilities[row]
            best = int(probabilities.argmax()) if flagged else None
            unclear = flagged and best == 0
            class_id = 0
            if flagged:
                class_id = None if unclear else best
            candidate = int(probabilities[1:].argmax()) + 1 if flagged else None

            top_factors = None
            if contributions is not None:
                row_contributions = contributions[row]
                feature_indices = sorted(range(len(self.feature_names)), key=lambda i: abs(row_contributions[i]), reverse=True)
                top_factors = [
                    {"feature": self.feature_names[i], "log_odds_delta": float(row_contributions[i])}
                    for i in feature_indices[:5]
                ]

            encoded_dict = {}
            for name, value in features.iloc[row].items():
                if pd.isna(value):
                    encoded_dict[name] = None
                else:
                    try:
                        encoded_dict[name] = float(value)
                    except (ValueError, TypeError):
                        encoded_dict[name] = str(value)

            output[index] = {
                "status":"scored", "model_id":self.manifest["model_id"], "flagged":bool(flagged),
                "inference_ms":latency,
                "binary_score":score, "threshold":threshold, "class_id":class_id,
                "class_score":float(probabilities[best]) if flagged and not unclear else None,
                "stage2_top_class_id":best,
                "stage2_top_score":float(probabilities[best]) if flagged else None,
                "best_attack_candidate_id":candidate,
                "best_attack_candidate_score":float(probabilities[candidate]) if flagged else None,
                "category_unclear":bool(unclear), "raw_inputs":item,
                "encoded_inputs":encoded_dict,
                "preprocessor_sha256":self.manifest["files"]["preprocessor.joblib"],
                "binary_contributions":top_factors,
            }
        return output
