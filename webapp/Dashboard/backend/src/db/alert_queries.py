"""MySQL queries for alert."""

def set_alert_status(store, alert_id, status):
    with store.transaction() as db:
        db.execute("SELECT id FROM alerts WHERE id=%s FOR UPDATE", (alert_id,))
        if not db.fetchone():
            return False
        db.execute(
            """UPDATE alerts SET status=%s,
               acknowledged_at=CASE WHEN %s='new' THEN NULL ELSE COALESCE(acknowledged_at, UTC_TIMESTAMP(6)) END,
               resolved_at=CASE WHEN %s='resolved' THEN COALESCE(resolved_at, UTC_TIMESTAMP(6)) ELSE NULL END
               WHERE id=%s""",
            (status, status, status, alert_id),
        )
    return True
