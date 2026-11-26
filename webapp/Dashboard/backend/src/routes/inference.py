"""HTTP endpoints for model scoring and data sources."""
from typing import Annotated, Literal

from fastapi import Body, HTTPException, Query, Request
from pydantic import BaseModel, Field
from ..controllers.inference import InferenceController
from ..models.live_capture import LiveCaptureSettings
from ..models.flow import CoreFlow


class CentralTestSample(BaseModel):
    record_id: str = Field(min_length=1, max_length=255)
    attack_category_id: int = Field(ge=0, le=5)
    features: CoreFlow


def mount_inference(app, manager, store, live):
    controller = InferenceController(manager, store)

    @app.get("/api/model")
    def model():
        return controller.model()

    @app.post("/api/predict")
    def predict(inputs: list[dict]):
        return controller.predict(inputs)

    @app.post("/api/traffic/central-test")
    def save_central_test(
        request: Request, samples: Annotated[list[CentralTestSample], Body(min_length=1, max_length=50)]
    ):
        return controller.save_central_test(samples, request)

    @app.get("/api/captures/{name}")
    def preview(name: str):
        return controller.preview(name)

    @app.post("/api/captures/{name}")
    def import_capture(name: str, request: Request):
        return controller.import_capture(name, request)

    @app.post("/api/capture-uploads")
    async def upload_capture(request: Request, name: str = Query(min_length=1, max_length=180)):
        return await controller.upload_capture(request, name)

    @app.get("/api/traffic/flows")
    def traffic_flows(limit: int = Query(50, ge=1, le=250), before_id: int | None = Query(None, ge=1),
                      capture_id: int | None = Query(None, ge=1), alerts_only: bool = False):
        return controller.traffic_flows(limit, before_id, capture_id, alerts_only)

    @app.get("/api/traffic/flows/{flow_id}/events")
    def protocol_events(flow_id: int):
        return controller.protocol_events(flow_id)

    @app.get("/api/traffic/alerts")
    def alerts(limit: int = Query(50, ge=1, le=250), before_id: int | None = Query(None, ge=1)):
        return controller.alerts(limit, before_id)

    @app.patch("/api/traffic/alerts/{alert_id}")
    def update_alert(alert_id: int, status: Literal["new", "acknowledged", "resolved"], request: Request):
        return controller.update_alert(alert_id, status, request)

    @app.get("/api/traffic/live")
    def live_status():
        return live.snapshot()

    @app.patch("/api/traffic/live/config")
    def update_live_config(settings: LiveCaptureSettings, request: Request):
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Update live capture settings from the local Flowwatch dashboard.")
        try:
            live.configure(settings.model_dump())
        except (OSError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        return live.snapshot()
