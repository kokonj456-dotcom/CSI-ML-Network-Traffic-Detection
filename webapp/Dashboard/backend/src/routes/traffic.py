"""HTTP endpoints for recorded traffic, alerts and live capture."""

from typing import Literal

from fastapi import Query, Request

from ..controllers.traffic import TrafficController


def mount_traffic(app, store, live):
    controller = TrafficController(store)

    @app.get("/api/traffic/flows")
    def traffic_flows(
        limit: int = Query(50, ge=1, le=250),
        before_id: int | None = Query(None, ge=1),
        capture_id: int | None = Query(None, ge=1),
        alerts_only: bool = False,
    ):
        return controller.traffic_flows(limit, before_id, capture_id, alerts_only)

    @app.get("/api/traffic/flows/{flow_id}/events")
    def protocol_events(flow_id: int):
        return controller.protocol_events(flow_id)

    @app.patch("/api/traffic/alerts/{alert_id}")
    def update_alert(
        alert_id: int,
        status: Literal["new", "acknowledged", "resolved"],
        request: Request,
    ):
        return controller.update_alert(alert_id, status, request)

    @app.get("/api/traffic/live")
    def live_status():
        return live.snapshot()
