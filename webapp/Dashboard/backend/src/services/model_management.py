"""Local feedback, training jobs and version registry for Flowwatch."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import subprocess
import sys
from threading import Lock, Thread
from time import sleep
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


class Management:
    def __init__(self, directory, existing_bundle, predictor_class, backup_dir, traffic_store=None):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = self.directory/"management.sqlite3"
        self.backup_dir = backup_dir.resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.active_path = self.backup_dir/"active-version.txt"
        self.predictor_class = predictor_class
        self.traffic_store = traffic_store
        self.base = self.bundle_path("baseline")
        if not self.base.exists():
            legacy_baseline = self.directory/"baseline"
            self.copy_backup(legacy_baseline if legacy_baseline.is_dir() else existing_bundle.resolve(), self.base)
        self.base = self.name_backup(self.base, "baseline")
        self.key = secrets.token_bytes(32)
        self.lock = Lock()
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY, created TEXT, status TEXT, payload TEXT, note TEXT, reviewed TEXT
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, created TEXT, status TEXT, config TEXT, finished TEXT, error TEXT
            );
            """)
            db.execute("UPDATE jobs SET status='failed', finished=?, error='Server restarted before completion' WHERE status='running'", (now(),))
            for job in db.execute("SELECT id FROM jobs WHERE status='completed'"):
                version = job["id"]
                legacy_bundle = self.directory/"jobs"/version/"bundle"
                destination = self.bundle_path(version)
                if legacy_bundle.is_dir() and not destination.exists():
                    self.copy_backup(legacy_bundle, destination)
                if destination.is_dir():
                    self.name_backup(destination, version)
            if self.active_path.is_file():
                self.version = self.active_path.read_text(encoding="utf-8").strip()
            else:
                legacy = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='activations'").fetchone()
                row = db.execute("SELECT version FROM activations ORDER BY id DESC LIMIT 1").fetchone() if legacy else None
                self.version = row["version"] if row else "baseline"
                self.save_active_version(self.version)
        self.load_warning = None
        try:
            self.predictor = self.load_candidate(self.version)
        except (OSError, ValueError, KeyError) as error:
            if self.version == "baseline":
                raise
            self.load_warning = f"Saved activation could not be restored. Baseline loaded: {error}"
            self.version = "baseline"
            self.predictor = self.load_candidate(self.version)

    def connect(self):
        # The caller's context manager commits/rolls back and closes the connection.
        return Connection(self.db)

    def save_active_version(self, version):
        with TemporaryDirectory(dir=self.backup_dir) as temp:
            staged = Path(temp)/self.active_path.name
            staged.write_text(version+"\n", encoding="utf-8")
            staged.replace(self.active_path)

    def copy_backup(self, source, destination):
        with TemporaryDirectory(dir=self.backup_dir) as temp:
            staged = Path(temp)/"bundle"
            shutil.copytree(source, staged)
            self.predictor_class(staged)
            staged.rename(destination)

    def name_backup(self, directory, version):
        prefix = "Base" if version == "baseline" else "FW"
        if directory.name == version:
            manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
            finished = (manifest.get("training") or {}).get("finished_at")
            timestamp = datetime.fromisoformat(finished) if finished else datetime.now(timezone.utc)
            local_time = timestamp.astimezone(timezone(timedelta(hours=7)))
        else:
            old_stamp = re.search(r"__(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_ICT(?:__.+|_\d+)?$", directory.name)
            if not old_stamp:
                return directory
            local_time = datetime.strptime(old_stamp[1], "%Y-%m-%d_%H-%M-%S")
        name = f"{prefix}-{local_time:%y%m%d-%H%M}"
        destination = self.backup_dir/name
        suffix = 2
        while destination.exists():
            destination = self.backup_dir/f"{name}_{suffix}"
            suffix += 1
        # Explorer and antivirus can briefly hold Windows directory handles.
        # The registry can still resolve a verified bundle from its version directory.
        for delay in (0, .25, .5, 1):
            if delay:
                sleep(delay)
            try:
                (directory/".registry-version").write_text(version, encoding="utf-8")
                return directory.rename(destination)
            except PermissionError:
                continue
        return directory

    def bundle_path(self, version):
        if version != "baseline" and not re.fullmatch(r"[0-9a-f]{32}", version):
            raise ValueError("Unknown model version.")
        for path in self.backup_dir.glob(f"*__{version}"):
            if path.is_dir():
                return path
        for marker in self.backup_dir.glob("*/.registry-version"):
            if marker.read_text(encoding="utf-8").strip() == version:
                return marker.parent
        return self.backup_dir/version

    def load_candidate(self, version):
        model = self.predictor_class(self.bundle_path(version))
        result = model.predict([{
            "duration":1, "bytes_forward":120, "bytes_backward":50,
            "protocol":"tcp", "service_group":"http", "conn_state_group":"established",
        }])
        if result[0]["status"] != "scored":
            raise ValueError("Inference smoke check failed.")
        return model

    def sign(self, encoded):
        return hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()

    def capture_receipt(self, row, file, prediction, alert_id=None):
        evidence = {
            "file":file, "frames":row["frames"], "timestamp":row["timestamp"],
            "src":row["src"], "dst":row["dst"], "sport":row["sport"], "dport":row["dport"],
            "raw":prediction.get("raw_inputs"), "prediction":prediction, "alert_id":alert_id,
        }
        encoded = json.dumps(evidence, separators=(",", ":"), allow_nan=False)
        return {"evidence":encoded,"signature":self.sign(encoded)}

    def report(self, body):
        flow = body.flow
        source = flow.get("source")
        reason = body.reason.strip()
        alert_id = flow.get("alert_id")
        if alert_id is not None:
            if not self.traffic_store or type(alert_id) is not int or not 0 < alert_id < 2**64:
                raise ValueError("A saved alert is required.")
            return self.traffic_store.report(alert_id, reason, body.evidence.strip())
        record = flow.get("record_id") or flow.get("id")
        receipt = flow.get("receipt")
        captured = None
        if receipt:
            try:
                encoded = receipt["evidence"]
                if hmac.compare_digest(self.sign(encoded), receipt["signature"]):
                    captured = json.loads(encoded)
            except (AttributeError, TypeError, ValueError, KeyError):
                pass
        if captured:
            source = "Analyzed PCAP"
            if not captured["prediction"]["flagged"]:
                raise ValueError("Only flagged capture flows can be reported.")
            if self.traffic_store:
                if captured.get("alert_id") is None:
                    raise ValueError("Import the capture before reporting its alert.")
                return self.traffic_store.report(captured["alert_id"], reason, body.evidence.strip())
            record = captured["file"]+":"+str(captured["frames"][0])
        elif source == "Analyzed PCAP":
            raise ValueError("Reload and analyze the capture again to attach verified evidence.")
        elif source not in ("CENTRAL Test", "Simulator", "PCAP Replay") or not record:
            raise ValueError("A supported flow is required.")
        payload = {
            "source":source, "record":str(record)[:240], "flow_id":str(flow.get("id",""))[:120],
            "eligible":bool(captured and captured["raw"]), "reason":reason,
            "evidence_note":body.evidence.strip(), "reviewer":"Local analyst", "proposed_label":"Benign",
            "actual_label":flow.get("actual_label"),
            "snapshot":captured or {key:flow.get(key) for key in ("prediction","raw","timestamp","src","dst","sport","dport")},
        }
        fingerprint = hashlib.sha256(json.dumps([source,payload["record"],payload["snapshot"].get("timestamp") if captured else None]).encode()).hexdigest()
        with self.connect() as db:
            try:
                db.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?)", (fingerprint,now(),"approved",json.dumps(payload),None,None))
            except sqlite3.IntegrityError as error:
                raise ValueError("This flow already has a feedback entry.") from error
        return fingerprint

    def review(self, identifier, body):
        if len(body.note.strip()) < 3:
            raise ValueError("Add a review note.")
        if identifier.startswith("mysql-"):
            if not self.traffic_store or not identifier[6:].isdigit():
                raise ValueError("Feedback is unavailable.")
            self.traffic_store.review(int(identifier[6:]), body.status, body.note.strip())
            return
        with self.connect() as db:
            changed = db.execute("UPDATE feedback SET status=?, note=?, reviewed=? WHERE id=? AND status='pending'",
                                 (body.status,body.note.strip(),now(),identifier))
            if not changed.rowcount:
                raise ValueError("Feedback is unavailable or already reviewed.")

    def get_bundle(self, version):
        directory = self.bundle_path(version)
        with (directory/"manifest.json").open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        with (directory/"evaluation.json").open(encoding="utf-8") as stream:
            evaluation = json.load(stream)
        return {"version":version,"manifest":manifest,"evaluation":evaluation}

    def overview(self):
        with self.lock, self.connect() as db:
            feedback = [dict(row) for row in db.execute("SELECT * FROM feedback ORDER BY created DESC")]
            jobs = [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC")]
            version, warning = self.version, self.load_warning
        for row in feedback:
            row.update(json.loads(row.pop("payload")))
        if self.traffic_store:
            feedback.extend(self.traffic_store.feedback())
            feedback.sort(key=lambda row: datetime.fromisoformat(row["created"]), reverse=True)
        for row in jobs:
            row["config"] = json.loads(row["config"])
            log = self.directory/"jobs"/row["id"]/"training.log"
            if log.is_file():
                with log.open("rb") as stream:
                    stream.seek(max(0,log.stat().st_size-2400))
                    row["log_tail"] = stream.read(2400).decode("utf-8", errors="replace")
        versions = []
        for identifier in ["baseline",*(row["id"] for row in jobs if row["status"]=="completed")]:
            try:
                versions.append(self.get_bundle(identifier))
            except (OSError, ValueError):
                continue
        return {
            "active":version,"warning":warning,"versions":versions,"feedback":feedback,
            "jobs":jobs,
            "dataset_counts":self.dataset_counts(),
            "parameter_defaults": m9_training_defaults(),
            "parameters":{name:{"min":low,"max":high,"default":default,"integer":kind is int}
                          for name,(low,high,default,kind) in PARAMETERS.items()},
        }

    def dataset_counts(self):
        try:
            audit = json.loads((CENTRAL/"reports"/"audit.json").read_text(encoding="utf-8"))
            return {name:audit["splits"][name]["rows"] for name in ("train","train_smote","validation","test")}
        except (OSError,ValueError,KeyError):
            return {}

    def start(self, body):
        config = normalize_config(body.config)
        identifier = uuid4().hex
        folder = self.directory/"jobs"/identifier
        with self.lock, self.connect() as db:
            if db.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():
                raise ValueError("A training job is already running.")
            selected = []
            for id_ in dict.fromkeys(body.feedback_ids):
                if id_.startswith("mysql-"):
                    reports = self.traffic_store.feedback(int(id_[6:])) if self.traffic_store and id_[6:].isdigit() else []
                    payload = reports[0] if reports else None
                    status = payload["status"] if payload else None
                else:
                    row = db.execute("SELECT status,payload FROM feedback WHERE id=?", (id_,)).fetchone()
                    payload = json.loads(row["payload"]) if row else None
                    status = row["status"] if row else None
                if status != "approved":
                    raise ValueError("Choose approved feedback only.")
                if not payload["eligible"]:
                    raise ValueError("Simulator and CENTRAL Test feedback cannot become training data.")
                selected.append({"id":id_,"source":payload["source"],"raw":payload["snapshot"]["raw"]})
            folder.mkdir(parents=True)
            config["feedback"] = selected
            (folder/"run.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?)", (identifier,now(),"running",json.dumps(config),None,None))
        Thread(target=self.train, args=(identifier,folder), daemon=True).start()
        return identifier

    def train(self, identifier, folder):
        status,error = "failed",None
        try:
            with (folder/"training.log").open("wb") as log:
                result = subprocess.run([sys.executable,"-u",str(TRAINER),"--run-config",str(folder/"run.json"),
                                          "--output",str(self.bundle_path(identifier)),"--managed-output"], cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                raise ValueError(f"Training exited with code {result.returncode}. See job output.")
            self.load_candidate(identifier)
            self.name_backup(self.bundle_path(identifier), identifier)
            status = "completed"
        except Exception as exc:
            error = str(exc)
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?, finished=?, error=? WHERE id=?", (status,now(),error,identifier))

    def activate(self, body):
        with self.lock, self.connect() as db:
            if body.version != "baseline" and not db.execute(
                "SELECT 1 FROM jobs WHERE id=? AND status='completed'",(body.version,)
            ).fetchone():
                raise ValueError("Only a completed candidate or the baseline can be activated.")
            model = self.load_candidate(body.version)
            self.save_active_version(body.version)
            self.version, self.predictor = body.version, model
            self.load_warning = None


class Connection(sqlite3.Connection):
    def __init__(self, path):
        super().__init__(path, timeout=10)
        self.row_factory = sqlite3.Row

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()
