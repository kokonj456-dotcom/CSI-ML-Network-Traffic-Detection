"""MySQL queries for alert."""
from .timestamps import wire_time


def alerts(store, limit, before_id):
    with store.transaction() as db:
        db.execute(
            """SELECT a.id, a.prediction_id, a.status, a.opened_at, a.acknowledged_at,
                      a.resolved_at, p.flow_id, p.model_id, p.binary_score, p.category_id
               FROM alerts a JOIN predictions p ON p.id=a.prediction_id
               WHERE (%s IS NULL OR a.id < %s) ORDER BY a.id DESC LIMIT %s""",
            (before_id, before_id, limit),
        )
        rows = db.fetchall()
    for row in rows:
        for key in ("opened_at", "acknowledged_at", "resolved_at"):
            row[key] = wire_time(row[key])
    return rows

def set_alert_status(store, alert_id, status):
    with store.transaction() as db:
        db.execute("SELECT id FROM alerts WHERE id=%s FOR UPDATE", (alert_id,))
        if not db.fetchone():
            return False
        db.execute(
            """UPDATE alerts SET status=%s,
               acknowledged_at=CASE WHEN %s='new' THEN NULL ELSE COALESCE(acknowledged_at, UTC_TIMESTAMP(6)) END,
               resolved_at=CASE WHEN %s='resolved' THEN COALESCE(resolved_at, UTC_TIMESTAMP(6)) ELSE NULL END
               WHERE id=%s""", (status, status, status, alert_id),
        )
    return True
