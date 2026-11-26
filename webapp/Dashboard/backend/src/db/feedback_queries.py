"""MySQL queries for feedback."""
from datetime import timezone
import json

from .timestamps import wire_time


def feedback(store, identifier=None):
    with store.transaction() as db:
        db.execute(
            """SELECT fp.id, fp.reason, fp.evidence_note, fp.status, fp.reported_at, fp.reviewed_at,
                      fp.review_note, p.inputs_json, f.source_type, f.started_at, c.original_name,
                      f.first_frame, f.id AS flow_id, INET6_NTOA(f.src_ip) AS src,
                      INET6_NTOA(f.dst_ip) AS dst, f.src_port, f.dst_port
               FROM false_positive_feedback fp JOIN alerts a ON a.id=fp.alert_id
               JOIN predictions p ON p.id=a.prediction_id JOIN traffic_flows f ON f.id=p.flow_id
               LEFT JOIN capture_files c ON c.id=f.capture_file_id
               WHERE (%s IS NULL OR fp.id=%s) ORDER BY fp.id DESC""", (identifier, identifier),
        )
        rows = db.fetchall()
    reports = []
    for row in rows:
        inputs = json.loads(row["inputs_json"])
        source = "Analyzed PCAP" if row["source_type"] == "pcap" else "Live Capture"
        reports.append({
            "id": f'mysql-{row["id"]}', "flow_id": f'DB-{row["flow_id"]}', "source": source,
            "record": f'{row["original_name"]}:{row["first_frame"]}' if row["original_name"] else str(row["flow_id"]),
            "eligible": bool(inputs.get("raw")), "status": row["status"], "reason": row["reason"],
            "evidence_note": row["evidence_note"], "proposed_label": "Benign",
            "created": wire_time(row["reported_at"]), "reviewed": wire_time(row["reviewed_at"]), "note": row["review_note"],
            "snapshot": {"raw": inputs.get("raw"), "prediction": inputs["prediction"],
                         "timestamp": int(row["started_at"].replace(tzinfo=timezone.utc).timestamp()*1000),
                         "src": row["src"], "dst": row["dst"], "sport": row["src_port"], "dport": row["dst_port"]},
        })
    return reports

def report(store, alert_id, reason, evidence):
    with store.transaction() as db:
        db.execute("""SELECT f.source_type FROM alerts a JOIN predictions p ON p.id=a.prediction_id
                      JOIN traffic_flows f ON f.id=p.flow_id WHERE a.id=%s FOR UPDATE""", (alert_id,))
        alert = db.fetchone()
        if not alert:
            raise ValueError("Alert does not exist.")
        if alert["source_type"] == "central_test":
            raise ValueError("CENTRAL Test records cannot be used as training feedback.")
        db.execute("SELECT id FROM false_positive_feedback WHERE alert_id=%s", (alert_id,))
        existing = db.fetchone()
        if existing:
            feedback_id = existing["id"]
        else:
            db.execute("INSERT INTO false_positive_feedback (alert_id,reason,evidence_note,status) VALUES (%s,%s,%s,'approved')",
                       (alert_id, reason, evidence or None))
            feedback_id = db.lastrowid
        db.execute(
            """UPDATE alerts SET status='resolved',
               acknowledged_at=COALESCE(acknowledged_at, UTC_TIMESTAMP(6)),
               resolved_at=COALESCE(resolved_at, UTC_TIMESTAMP(6)) WHERE id=%s""", (alert_id,),
        )
        return f"mysql-{feedback_id}"

def review(store, identifier, status, note):
    with store.transaction() as db:
        db.execute(
            """UPDATE false_positive_feedback SET status=%s,review_note=%s,reviewed_at=UTC_TIMESTAMP(6)
               WHERE id=%s AND status='pending'""", (status, note, identifier),
        )
        if not db.rowcount:
            raise ValueError("Feedback is unavailable or already reviewed.")
