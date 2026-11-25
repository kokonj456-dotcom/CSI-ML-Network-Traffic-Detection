"""Train and evaluate a paired CENTRAL XGBoost model bundle for Flowwatch."""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from webapp.Dashboard.backend.src.models.central_contract import (  # noqa: E402
    CLASS_NAMES, CORE, NAMES, transform_features,
)

CENTRAL = ROOT / "data-pipeline" / "CENTRAL" / "output"
DEFAULT_BUNDLE = CENTRAL / "flowwatch_bundle"
CLASSES = list(range(len(CLASS_NAMES)))
PARAMETERS = {
    "n_estimators": (1, 500, 140, int),
    "max_depth": (1, 12, 6, int),
    "learning_rate": (.005, .5, .12, float),
    "subsample": (.1, 1, 1, float),
    "colsample_bytree": (.1, 1, 1, float),
    "min_child_weight": (0, 50, 1, float),
    "gamma": (0, 50, 0, float),
    "reg_alpha": (0, 50, 0, float),
    "reg_lambda": (0, 50, 1, float),
}
STRATEGIES = ("baseline", "class_weighted", "smotenc")


def normalize_config(config, trees=140, budget=.05):
    if not isinstance(config, dict):
        raise ValueError("Expected training configuration.")
    strategy = config.get("strategy", "compare")
    if strategy not in (*STRATEGIES, "compare"):
        raise ValueError("Unknown training strategy.")
    max_fpr = config.get("max_validation_fpr", budget)
    if type(max_fpr) not in (int, float) or not 0 <= max_fpr <= 1:
        raise ValueError("Validation FPR must be between 0 and 1.")
    result = {"strategy":strategy, "max_validation_fpr":max_fpr}
    for stage in ("stage1", "stage2"):
        supplied = config.get(stage, {})
        if not isinstance(supplied, dict) or set(supplied)-set(PARAMETERS):
            raise ValueError(f"Unknown {stage} parameter.")
        result[stage] = {}
        for name,(low,high,default,kind) in PARAMETERS.items():
            value = supplied.get(name, trees if name=="n_estimators" else default)
            if type(value) not in (int,float) or not low <= value <= high or kind is int and value != int(value):
                raise ValueError(f"{stage}.{name} must be between {low} and {high}.")
            result[stage][name] = kind(value)
    return result


def prepare_feedback(rows, preprocessor):
    excluded = set()
    for split in ("train", "validation", "test"):
        core = pd.read_csv(CENTRAL/"splits"/split/"features.csv", usecols=CORE)[CORE]
        excluded.update(pd.util.hash_pandas_object(core, index=False))
    accepted, skipped = [], []
    for row in rows:
        if row["source"] not in ("Analyzed PCAP", "Live Capture"):
            skipped.append({"id":row["id"],"reason":"source is ineligible"})
            continue
        raw = pd.DataFrame([row["raw"]], columns=CORE).astype({k:float for k in CORE[:3]})
        group = pd.util.hash_pandas_object(raw, index=False).iloc[0]
        if group in excluded:
            skipped.append({"id":row["id"],"reason":"duplicate feedback or CENTRAL feature group"})
            continue
        excluded.add(group)
        accepted.append(row)
    if not accepted:
        return None, [], skipped
    raw = pd.DataFrame([row["raw"] for row in accepted]).assign(record_id=[row["id"] for row in accepted])
    return transform_features(raw,preprocessor)[NAMES], [row["id"] for row in accepted], skipped


def append_feedback(data, features):
    if features is None:
        return data
    frame,binary,multi = data
    benign = np.zeros(len(features),dtype=int)
    return pd.concat([frame,features],ignore_index=True), np.concatenate([binary,benign]), np.concatenate([multi,benign])



def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_split(split):
    folder = CENTRAL / "feature_engineering" / split
    source = CENTRAL / "splits" / split
    features = pd.read_csv(folder / "features.csv")
    labels = pd.read_csv(source / "labels.csv", usecols=["record_id", "label_binary", "attack_category_id"])
    metadata = pd.read_csv(source / "metadata.csv", usecols=["record_id", "split_group", "source_dataset"])
    if not (features.record_id.equals(labels.record_id) and labels.record_id.equals(metadata.record_id)):
        raise ValueError(f"Record alignment failed for {split}")
    return features[NAMES], labels.label_binary.to_numpy(), labels.attack_category_id.to_numpy(), metadata


def load_smote():
    folder = CENTRAL / "splits" / "train_smote"
    features = pd.read_csv(folder / "features_encoded_19.csv")
    labels = pd.read_csv(folder / "labels.csv", usecols=["record_id", "label_binary", "attack_category_id"])
    if not features.record_id.equals(labels.record_id):
        raise ValueError("SMOTENC record alignment failed")
    return features[NAMES], labels.label_binary.to_numpy(), labels.attack_category_id.to_numpy()


def decisions(score, probabilities, threshold):
    flagged = score >= threshold
    return np.where(flagged, probabilities[:, 1:].argmax(axis=1) + 1, 0)


def binary_metrics(actual, flagged):
    tn, fp, fn, tp = confusion_matrix(actual, flagged, labels=[0, 1]).ravel()
    return {
        "f1": float(f1_score(actual, flagged, zero_division=0)),
        "fpr": float(fp / (fp + tn)) if fp + tn else None,
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def evaluation(binary, multi, score, probabilities, threshold):
    flagged = score >= threshold
    predicted = decisions(score, probabilities, threshold)
    precision, recall, f1, support = precision_recall_fscore_support(
        multi, predicted, labels=CLASSES, zero_division=0
    )
    disagreements = flagged & (probabilities.argmax(axis=1) == 0)
    return {
        "rows": len(multi),
        "binary": binary_metrics(binary, flagged),
        "forced_category_macro_f1": float(np.mean(f1)),
        "category_unclear": int(disagreements.sum()),
        "false_normal_stage2": {
            name: int(np.sum(disagreements & (multi == index)))
            for index, name in enumerate(CLASS_NAMES)
        },
        "per_class_best_attack_candidate": {
            name: {"precision": float(p), "recall": float(r), "f1": float(f), "support": int(n)}
            for name, p, r, f, n in zip(CLASS_NAMES, precision, recall, f1, support)
        },
        "confusion_matrix_best_attack_candidate": confusion_matrix(multi, predicted, labels=CLASSES).tolist(),
    }


def fit_candidate(features, binary, multi, validation, weighted, jobs, config):
    common = dict(tree_method="hist", n_jobs=jobs, random_state=42)
    stage1 = XGBClassifier(**common, **config["stage1"], objective="binary:logistic")
    stage2 = XGBClassifier(**common, **config["stage2"], objective="multi:softprob", num_class=6)
    max_fpr = config["max_validation_fpr"]
    stage1.fit(features, binary, sample_weight=compute_sample_weight("balanced", binary) if weighted else None)
    stage2.fit(features, multi, sample_weight=compute_sample_weight("balanced", multi) if weighted else None)
    X_val, y_bin, y_multi, _ = validation
    score = stage1.predict_proba(X_val)[:, 1]
    probabilities = stage2.predict_proba(X_val)
    thresholds = sorted(set(np.linspace(.05,.99,95).round(2)) | {.995,.999,1.0})
    points = [(float(threshold), binary_metrics(y_bin, score >= threshold)) for threshold in thresholds]
    eligible = [point for point in points if point[1]["fpr"] <= max_fpr]
    if not eligible:
        eligible = [min(points, key=lambda point: point[1]["fpr"])]
    threshold, _ = max(eligible, key=lambda item: (item[1]["f1"], -item[1]["fpr"]))
    return stage1, stage2, threshold, evaluation(y_bin,y_multi,score,probabilities,threshold)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--trees", type=int, default=140)
    parser.add_argument("--max-validation-fpr", type=float, default=.05)
    parser.add_argument("--run-config", type=Path)
    parser.add_argument("--managed-output", action="store_true", help="Write directly to a registry-managed job directory.")
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc).isoformat()
    requested = json.loads(args.run_config.read_text(encoding="utf-8")) if args.run_config else {}
    config = normalize_config(requested, args.trees, args.max_validation_fpr)
    if not 0 <= args.max_validation_fpr <= 1:
        parser.error("Validation FPR must be between 0 and 1.")
    output = args.output.resolve()
    if output.exists():
        parser.error(f"Bundle already exists: {output}. Choose a new versioned directory.")
    train = load_split("train")
    validation = load_split("validation")
    if set(train[3].split_group) & set(validation[3].split_group):
        raise ValueError("Training feature groups overlap validation")
    preprocessor = CENTRAL / "feature_engineering" / "preprocessor.joblib"
    prep = joblib.load(preprocessor)
    fit_ids = pd.read_csv(CENTRAL/"splits/train/labels.csv", usecols=["record_id"]).record_id
    if hashlib.sha256("\n".join(fit_ids).encode()).hexdigest() != prep["fit_record_ids_sha256"]:
        raise ValueError("Preprocessor provenance does not match train IDs")
    test_paths = [CENTRAL/"feature_engineering"/"test"/"features.csv",
                  CENTRAL/"splits"/"test"/"labels.csv",CENTRAL/"splits"/"test"/"metadata.csv"]
    evaluation_fingerprint = hashlib.sha256("".join(digest(path) for path in test_paths).encode()).hexdigest()
    feedback,feedback_ids,feedback_skipped = prepare_feedback(requested["feedback"],prep) if requested.get("feedback") else (None,[],[])
    candidates = {}
    candidate_sizes = {}
    selected = None
    for name, data, weighted in [
        ("baseline", train[:3], False), ("class_weighted", train[:3], True), ("smotenc", None, False)
    ]:
        if config["strategy"] not in ("compare", name):
            continue
        data = append_feedback(load_smote() if name=="smotenc" else data,feedback)
        print(f"Training {name} ({len(data[0]):,} rows)", flush=True)
        stage1,stage2,threshold,val = fit_candidate(*data,validation,weighted,args.jobs,config)
        candidate_sizes[name] = len(data[0])
        candidates[name] = {"threshold":threshold,"validation":val}
        key = (val["binary"]["fpr"] <= config["max_validation_fpr"], val["forced_category_macro_f1"], val["binary"]["f1"])
        if selected is None or key > selected[0]:
            selected = (key,name,stage1,stage2,threshold)
        print(name, "threshold", threshold, "binary", val["binary"], "macro F1", val["forced_category_macro_f1"], flush=True)
    _,name,stage1,stage2,threshold = selected
    X,y_binary,y_multi,metadata = load_split("test")
    score = stage1.predict_proba(X)[:, 1]
    probabilities = stage2.predict_proba(X)
    excluded = set(train[3].split_group) | set(validation[3].split_group)
    disjoint = ~metadata.split_group.isin(excluded).to_numpy()
    per_source = {}
    for source in sorted(metadata.source_dataset.unique()):
        mask = (metadata.source_dataset == source).to_numpy()
        per_source[source] = evaluation(y_binary[mask],y_multi[mask],score[mask],probabilities[mask],threshold)
    report = {
        "candidate": name, "validation_fpr_budget": config["max_validation_fpr"],
        "candidates": candidates,
        "test_full": evaluation(y_binary,y_multi,score,probabilities,threshold),
        "test_feature_group_disjoint": evaluation(y_binary[disjoint],y_multi[disjoint],score[disjoint],probabilities[disjoint],threshold),
        "test_by_source": per_source,
        "scope": "Offline dataset evaluation. Feature-group disjointness does not establish capture or deployment independence.",
    }
    if evaluation_fingerprint != hashlib.sha256("".join(digest(path) for path in test_paths).encode()).hexdigest():
        raise ValueError("Evaluation files changed during training.")
    output.parent.mkdir(parents=True, exist_ok=True)
    workspace = nullcontext() if args.managed_output else TemporaryDirectory(dir=output.parent)
    with workspace as temporary:
        staging = output if args.managed_output else Path(temporary)/"bundle"
        staging.mkdir()
        stage1.save_model(staging/"binary.json")
        stage2.save_model(staging/"multiclass.json")
        shutil.copyfile(preprocessor, staging/"preprocessor.joblib")
        files = {name:digest(staging/name) for name in ("binary.json","multiclass.json","preprocessor.joblib")}
        manifest = {
            "model_id": "flowwatch-central-"+hashlib.sha256(("".join(files.values())+str(threshold)).encode()).hexdigest()[:14],
            "schema_version": prep["schema_version"], "feature_names": NAMES, "class_names": CLASS_NAMES,
            "threshold": threshold, "files": files, "fit_record_ids_sha256": prep["fit_record_ids_sha256"],
            "dataset_audit_sha256": digest(CENTRAL/"reports/audit.json"),
            "candidate":name,"scope":"diagnostic", "evaluation_sha256":evaluation_fingerprint,
            "training":{"started_at":started_at,"finished_at":datetime.now(timezone.utc).isoformat(),
                        "config":config,"seed":42,"feedback_ids":feedback_ids,"feedback_skipped":feedback_skipped,
                        "train_rows": candidate_sizes[name],
                        "validation_rows":len(validation[0]),"test_rows":len(X)},
        }
        for filename,payload in [("manifest.json",manifest),("evaluation.json",report)]:
            (staging/filename).write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
        if not args.managed_output:
            staging.rename(output)
    print("Bundle", output, "selected", name, "threshold", threshold, flush=True)


if __name__ == "__main__":
    main()

