"""MySQL persistence for capture analysis and false-positive feedback."""
from contextlib import contextmanager
from hashlib import file_digest
import json
from os import environ

from dotenv import dotenv_values
from mysql.connector import connect

from ..config import DASHBOARD
from . import alert_queries, feedback_queries
from .timestamps import utc_time, wire_time


def mysql_settings():
    config = {**dotenv_values(DASHBOARD / ".env"), **environ}
    user = config.get("FLOWWATCH_MYSQL_USER")
    password = config.get("FLOWWATCH_MYSQL_PASSWORD")
    if not user or not password:
        return None
    return {
        "host": config.get("FLOWWATCH_MYSQL_HOST", "127.0.0.1"),
        "port": int(config.get("FLOWWATCH_MYSQL_PORT", "3306")),
        "database": config.get("FLOWWATCH_MYSQL_DATABASE", "flowwatch"),
        "user": user,
        "password": password,
        "connection_timeout": 5,
        "time_zone": "+00:00",
    }


class MySQLStore:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def transaction(self):
        with connect(**self.settings) as connection:
            with connection.cursor(dictionary=True) as cursor:
                yield cursor
            connection.commit()

    def save_capture(self, path, records, predictions, original_name=None):
        with path.open("rb") as stream:
            fingerprint = file_digest(stream, "sha256").digest()
        identifiers = []
        with self.transaction() as db:
            db.execute(
                """INSERT INTO capture_files (original_name, storage_path, sha256)
                   VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)""",
                (original_name or path.name, str(path), fingerprint),
            )
            capture_id = db.lastrowid
            identifiers = self.save_records(db, records, predictions, capture_id=capture_id)
        return capture_id, identifiers

    def save_live(self, interface, records, predictions):
        with self.transaction() as db:
            return self.save_records(db, records, predictions, interface=interface)

    def save_central_test(self, records, predictions):
        with self.transaction() as db:
            return self.save_records(db, records, predictions, source_type="central_test")

    @staticmethod
    def save_records(db, records, predictions, capture_id=None, interface=None, source_type=None):
        identifiers = []
        for flow, prediction in zip(records, predictions, strict=True):
            raw = flow["raw"]
            first_frame = next(iter(flow["frames"]), None)
            existing = None
            if capture_id is not None:
                db.execute(
                    "SELECT id FROM traffic_flows WHERE capture_file_id=%s AND first_frame=%s",
                    (capture_id, first_frame),
                )
                existing = db.fetchone()
            if existing:
                flow_id = existing["id"]
            else:
                db.execute(
                    """INSERT INTO traffic_flows (
                       capture_file_id, first_frame, source_type, interface_name, started_at, ended_at, src_ip, dst_ip,
                       src_port, dst_port, transport_protocol, service_group, connection_state,
                       packets_forward, packets_backward, bytes_forward, bytes_backward
                       ) VALUES (%s,%s,%s,%s,%s,%s,INET6_ATON(%s),INET6_ATON(%s),%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (capture_id, first_frame, source_type or ('pcap' if capture_id is not None else 'live_capture'),
                     interface, utc_time(flow["started_at"]), utc_time(flow["ended_at"]),
                     flow["src"], flow["dst"], flow["sport"], flow["dport"], raw["protocol"],
                     raw["service_group"], raw["conn_state_group"], flow["packets_forward"],
                     flow["packets_backward"], raw["bytes_forward"], raw["bytes_backward"]),
                )
                flow_id = db.lastrowid
                if flow["protocol_events"]:
                    db.executemany(
                        """INSERT INTO flow_protocol_events
                           (flow_id, observed_at, protocol, frame_number, details_json)
                           VALUES (%s,%s,%s,%s,%s)""",
                        [(flow_id, utc_time(event["at"]), event["protocol"], event["frame"],
                          json.dumps(event["details"])) for event in flow["protocol_events"]],
                    )
            db.execute(
                """INSERT INTO predictions
                   (flow_id, model_id, status, binary_score, threshold_used, is_flagged, category_id,
                   category_score, inputs_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)""",
                (flow_id, prediction["model_id"], prediction["status"], prediction.get("binary_score"),
                 prediction.get("threshold"), prediction.get("flagged"), prediction.get("class_id"),
                 prediction.get("class_score"), json.dumps({"raw": raw, "prediction": prediction,
                                                               "frames": flow["frames"],
                                                               "protocol_observation": flow["protocol_observation"],
                                                               "dataset": flow.get("dataset")}, allow_nan=False)),
            )
            prediction_id = db.lastrowid
            alert_id = None
            if prediction.get("flagged"):
                db.execute(
                    """INSERT INTO alerts (prediction_id) VALUES (%s)
                       ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)""", (prediction_id,),
                )
                alert_id = db.lastrowid
            identifiers.append({"flow_id": flow_id, "prediction_id": prediction_id, "alert_id": alert_id})
        return identifiers

    def flows(self, limit, before_id, capture_id=None, alerts_only=False):
        prediction_lookup = "SELECT MAX(p2.id) FROM predictions p2 WHERE p2.flow_id=f.id"
        if alerts_only:
            prediction_lookup += " AND EXISTS (SELECT 1 FROM alerts a2 WHERE a2.prediction_id=p2.id)"
        with self.transaction() as db:
            db.execute(
                f"""SELECT f.id, f.source_type, f.started_at, f.ended_at, f.interface_name,
                          INET6_NTOA(f.src_ip) AS src, INET6_NTOA(f.dst_ip) AS dst,
                          f.src_port, f.dst_port, f.transport_protocol, f.service_group, f.connection_state,
                          f.packets_forward, f.packets_backward, f.bytes_forward, f.bytes_backward,
                          f.capture_file_id, c.original_name AS capture_file, p.model_id, p.status AS prediction_status,
                          p.binary_score, p.threshold_used, p.category_id, p.category_score, p.inputs_json,
                          a.id AS alert_id, a.status AS alert_status,
                          EXISTS (SELECT 1 FROM false_positive_feedback fp WHERE fp.alert_id=a.id) AS false_positive_reported
                   FROM traffic_flows f LEFT JOIN capture_files c ON c.id=f.capture_file_id
                   LEFT JOIN predictions p ON p.id=({prediction_lookup})
                   LEFT JOIN alerts a ON a.prediction_id=p.id
                   WHERE (%s IS NULL OR f.id < %s) AND (%s IS NULL OR f.capture_file_id=%s)
                     AND (NOT %s OR a.id IS NOT NULL)
                   ORDER BY f.id DESC LIMIT %s""",
                (before_id, before_id, capture_id, capture_id, alerts_only, limit),
            )
            rows = db.fetchall()
        for row in rows:
            row["evidence"] = json.loads(row.pop("inputs_json") or "{}")
            for key in ("started_at", "ended_at"):
                row[key] = wire_time(row[key])
        return rows

    def flow_count(self, capture_id=None, alerts_only=False):
        """Return the full matching flow count, independent of the page cursor."""
        with self.transaction() as db:
            db.execute(
                """SELECT COUNT(*) AS total
                   FROM traffic_flows f
                   WHERE (%s IS NULL OR f.capture_file_id=%s)
                     AND (NOT %s OR EXISTS (
                       SELECT 1 FROM predictions p
                       JOIN alerts a ON a.prediction_id=p.id
                       WHERE p.flow_id=f.id
                     ))""",
                (capture_id, capture_id, alerts_only),
            )
            return db.fetchone()["total"]

    def protocol_events(self, flow_id):
        with self.transaction() as db:
            db.execute("SELECT id FROM traffic_flows WHERE id=%s", (flow_id,))
            if not db.fetchone():
                return None
            db.execute(
                """SELECT observed_at, protocol, frame_number, details_json FROM flow_protocol_events
                   WHERE flow_id=%s ORDER BY observed_at, id""", (flow_id,),
            )
            rows = db.fetchall()
        for row in rows:
            row["observed_at"] = wire_time(row["observed_at"])
            row["details"] = json.loads(row.pop("details_json"))
        return rows

    def alerts(self, limit, before_id):
        return alert_queries.alerts(self, limit, before_id)

    def set_alert_status(self, alert_id, status):
        return alert_queries.set_alert_status(self, alert_id, status)

    def feedback(self, identifier=None):
        return feedback_queries.feedback(self, identifier)

    def report(self, alert_id, reason, evidence):
        return feedback_queries.report(self, alert_id, reason, evidence)

    def review(self, identifier, status, note):
        return feedback_queries.review(self, identifier, status, note)
