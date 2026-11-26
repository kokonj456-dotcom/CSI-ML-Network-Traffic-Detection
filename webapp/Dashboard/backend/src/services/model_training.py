"""Prepare training data, run candidate jobs, and record their outcome."""
from datetime import datetime, timezone
import json
import subprocess
import sys
from threading import Thread
from uuid import uuid4

from ..config import ROOT, TRAINER


sys.path.insert(0, str(TRAINER.parent))
from train_flowwatch import CENTRAL, PARAMETERS, normalize_config  # noqa: E402


def m9_training_defaults():
    path = ROOT / "experiments/scaling_and_domain_shift/models/production/optuna_best_params.json"
    tuned = json.loads(path.read_text(encoding="utf-8"))
    return normalize_config({
        "stage1": tuned["binary_best"],
        "stage2": tuned["multiclass_best"],
    }, trees=250)


def now():
    return datetime.now(timezone.utc).isoformat()


def dataset_counts():
    try:
        audit = json.loads((CENTRAL/"reports"/"audit.json").read_text(encoding="utf-8"))
        return {name:audit["splits"][name]["rows"] for name in ("train","train_smote","validation","test")}
    except (OSError,ValueError,KeyError):
        return {}

def select_training_feedback(manager, db, feedback_ids):
    selected = []
    for feedback_id in dict.fromkeys(feedback_ids):
        if feedback_id.startswith("mysql-"):
            mysql_id = feedback_id.removeprefix("mysql-")
            reports = []
            if manager.traffic_store and mysql_id.isdigit():
                reports = manager.traffic_store.feedback(int(mysql_id))
            payload = reports[0] if reports else None
            status = payload["status"] if payload else None
        else:
            row = db.execute(
                "SELECT status,payload FROM feedback WHERE id=?", (feedback_id,)
            ).fetchone()
            payload = json.loads(row["payload"]) if row else None
            status = row["status"] if row else None

        if status != "approved":
            raise ValueError("Choose approved feedback only.")
        if not payload["eligible"]:
            raise ValueError("Simulator and CENTRAL Test feedback cannot become training data.")
        selected.append({
            "id": feedback_id,
            "source": payload["source"],
            "raw": payload["snapshot"]["raw"],
        })
    return selected

def start_training_job(manager, body):
    config = normalize_config(body.config)
    identifier = uuid4().hex
    folder = manager.directory/"jobs"/identifier
    with manager.lock, manager.connect() as db:
        if db.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():
            raise ValueError("A training job is already running.")
        selected = manager.training_feedback(db, body.feedback_ids)
        folder.mkdir(parents=True)
        config["feedback"] = selected
        (folder/"run.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?)", (identifier,now(),"running",json.dumps(config),None,None))
    Thread(target=manager.train, args=(identifier,folder), daemon=True).start()
    return identifier

def run_training_job(manager, identifier, folder):
    status, error = "failed", None
    try:
        command = [
            sys.executable, "-u", str(TRAINER),
            "--run-config", str(folder/"run.json"),
            "--output", str(manager.registry.bundle_path(identifier)),
            "--managed-output",
        ]
        with (folder/"training.log").open("wb") as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise ValueError(f"Training exited with code {result.returncode}. See job output.")
        manager.registry.load_candidate(identifier)
        manager.registry.name_backup(manager.registry.bundle_path(identifier), identifier)
        status = "completed"
    except Exception as exc:
        error = str(exc)
    with manager.connect() as db:
        db.execute("UPDATE jobs SET status=?, finished=?, error=? WHERE id=?", (status,now(),error,identifier))
