"""Load a validated paired model and score normalized flows."""
import hashlib
import json
from time import perf_counter

import joblib
import pandas as pd
import xgboost as xgb

from ..models.central_contract import CLASS_NAMES, NAMES, transform_features
from ..config import capture_files
from ..models.flow import CoreFlow


class Predictor:
    def __init__(self, directory):
        report = json.loads((directory/"evaluation.json").read_text(encoding="utf-8"))
        self.evaluation = {
            name: {"rows": report[name]["rows"], "binary": report[name]["binary"]}
            for name in ("test_full", "test_feature_group_disjoint")
        }
        self.manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
        if self.manifest["feature_names"] != NAMES or self.manifest["class_names"] != CLASS_NAMES:
            raise ValueError("Bundle does not match the CENTRAL feature/class contract")
        if not 0 <= self.manifest["threshold"] <= 1:
            raise ValueError("Threshold is outside [0, 1]")
        for filename in ("binary.json", "multiclass.json", "preprocessor.joblib"):
            with (directory/filename).open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != self.manifest["files"][filename]:
                raise ValueError(f"Fingerprint mismatch: {filename}")
        self.prep = joblib.load(directory/"preprocessor.joblib")
        for key in ("fit_record_ids_sha256", "schema_version"):
            if self.prep[key] != self.manifest[key]:
                raise ValueError(f"Preprocessor does not match manifest: {key}")
        if self.prep["model_feature_names"] != NAMES:
            raise ValueError("Preprocessor has incorrect feature columns")
        self.binary = xgb.XGBClassifier(n_jobs=2)
        self.multi = xgb.XGBClassifier(n_jobs=2)
        self.binary.load_model(directory/"binary.json")
        self.multi.load_model(directory/"multiclass.json")
        for model, count in ((self.binary, 2), (self.multi, 6)):
            if model.get_booster().feature_names != NAMES or list(model.classes_) != list(range(count)):
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
        raw = pd.DataFrame([item for _, item in valid]).assign(record_id=[str(i) for i, _ in valid])
        X = transform_features(raw, self.prep)[NAMES]
        scores = self.binary.predict_proba(X)[:, 1]
        probabilities = self.multi.predict_proba(X)
        latency = (perf_counter() - start) * 1000 / len(valid)
        contributions = self.binary.get_booster().predict(xgb.DMatrix(X), pred_contribs=True) if explain else None
        threshold = self.manifest["threshold"]
        for row,(index, item) in enumerate(valid):
            score = float(scores[row])
            flagged = score >= threshold
            best = int(probabilities[row].argmax()) if flagged else None
            unclear = flagged and best == 0
            class_id = None if unclear else best if flagged else 0
            candidate = int(probabilities[row,1:].argmax())+1 if flagged else None
            output[index] = {
                "status":"scored", "model_id":self.manifest["model_id"], "flagged":bool(flagged),
                "inference_ms":latency,
                "binary_score":score, "threshold":threshold, "class_id":class_id,
                "class_score":float(probabilities[row,best]) if flagged and not unclear else None,
                "stage2_top_class_id":best,
                "stage2_top_score":float(probabilities[row,best]) if flagged else None,
                "best_attack_candidate_id":candidate,
                "best_attack_candidate_score":float(probabilities[row,candidate]) if flagged else None,
                "category_unclear":bool(unclear), "raw_inputs":item,
                "encoded_inputs":{name:float(value) for name,value in X.iloc[row].items()},
                "preprocessor_sha256":self.manifest["files"]["preprocessor.joblib"],
                "binary_contributions": [
                    {"feature":NAMES[i],"log_odds_delta":float(row_contributions[i])}
                    for i in sorted(range(len(NAMES)),key=lambda i:abs(row_contributions[i]),reverse=True)[:5]
                ] if (row_contributions := contributions[row] if contributions is not None else None) is not None else None,
            }
        return output
