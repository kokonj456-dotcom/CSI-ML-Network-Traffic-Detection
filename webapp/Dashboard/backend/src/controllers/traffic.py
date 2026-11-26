"""Read saved flows and manage alert status."""
from fastapi import HTTPException

from .request_checks import SavedTrafficController


class TrafficController(SavedTrafficController):
    @staticmethod
    def page(rows, limit):
        return rows[:limit], rows[limit-1]["id"] if len(rows)>limit else None

    def traffic_flows(self, limit, before_id, capture_id, alerts_only=False):
        store = self.require_store()
        rows, next_id = self.page(store.flows(limit+1, before_id, capture_id, alerts_only), limit)
        return {"flows": rows, "next_before_id": next_id,
                "total_flows": store.flow_count(capture_id, alerts_only)}

    def protocol_events(self, flow_id):
        rows = self.require_store().protocol_events(flow_id)
        if rows is None:
            raise HTTPException(404, "Flow does not exist.")
        return {"events": rows}

    def alerts(self, limit, before_id):
        rows, next_id = self.page(self.require_store().alerts(limit+1, before_id), limit)
        return {"alerts": rows, "next_before_id": next_id}

    def update_alert(self, alert_id, status, request):
        self.require_local_write(request)
        if not self.require_store().set_alert_status(alert_id, status):
            raise HTTPException(404, "Alert does not exist.")
        return {"status": status}
