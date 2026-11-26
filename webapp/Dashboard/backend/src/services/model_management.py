"""Local feedback, training jobs and version registry for Flowwatch."""
from datetime import datetime
import hashlib
import hmac
import json
import secrets
import sqlite3
from threading import Lock


from .model_registry import ModelRegistry
from .model_training import (
    PARAMETERS, dataset_counts, m9_training_defaults, now,
    run_training_job, select_training_feedback, start_training_job,
)

class Management:
    def __init__(self, directory, existing_bundle, predictor_class, backup_dir, traffic_store=None):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = self.directory/"management.sqlite3"
        self.registry = ModelRegistry(backup_dir, predictor_class)
        self.traffic_store = traffic_store
        self.registry.prepare_baseline(existing_bundle, self.directory/"baseline")
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
                self.registry.restore_backup(version, legacy_bundle)
            if self.registry.active_path.is_file():
                self.version = self.registry.active_path.read_text(encoding="utf-8").strip()
            else:
                legacy = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='activations'").fetchone()
                row = db.execute("SELECT version FROM activations ORDER BY id DESC LIMIT 1").fetchone() if legacy else None
                self.version = row["version"] if row else "baseline"
                self.registry.save_active_version(self.version)
        self.load_warning = None
        try:
            self.predictor = self.registry.load_candidate(self.version)
        except (OSError, ValueError, KeyError) as error:
            if self.version == "baseline":
                raise
            self.load_warning = f"Saved activation could not be restored. Baseline loaded: {error}"
            self.version = "baseline"
            self.predictor = self.registry.load_candidate(self.version)

    def connect(self):
        # The caller's context manager commits/rolls back and closes the connection.
        return Connection(self.db)

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

    def overview(self):
        with self.lock, self.connect() as db:
            feedback = [dict(row) for row in db.execute("SELECT * FROM feedback ORDER BY created DESC")]
            jobs = [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC")]
            version, warning = self.version, self.load_warning
        # A job is shown as a model version only while it is running or when its
        # completed bundle is still present and readable in the model registry.
        visible_jobs = []
        for row in jobs:
            if row["status"] == "running":
                visible_jobs.append(row)
                continue
            if row["status"] != "completed":
                continue
            try:
                bundle = self.registry.get_bundle(row["id"])
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
            if bundle["manifest"].get("model_id"):
                visible_jobs.append(row)
        jobs = visible_jobs
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
                versions.append(self.registry.get_bundle(identifier))
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
        return dataset_counts()

    def training_feedback(self, db, feedback_ids):
        return select_training_feedback(self, db, feedback_ids)

    def start(self, body):
        return start_training_job(self, body)

    def train(self, identifier, folder):
        return run_training_job(self, identifier, folder)

    def activate(self, body):
        with self.lock, self.connect() as db:
            if body.version != "baseline" and not db.execute(
                "SELECT 1 FROM jobs WHERE id=? AND status='completed'",(body.version,)
            ).fetchone():
                raise ValueError("Only a completed candidate or the baseline can be activated.")
            model = self.registry.load_candidate(body.version)
            self.registry.save_active_version(body.version)
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
