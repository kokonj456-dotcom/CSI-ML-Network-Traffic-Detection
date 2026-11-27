"""HTTP endpoints for model scoring and CENTRAL Test."""

from typing import Annotated

from fastapi import Body, Request
from pydantic import BaseModel, Field
from ..controllers.inference import InferenceController
from ..models.flow import CoreFlow


class CentralTestSample(BaseModel):
    record_id: str = Field(min_length=1, max_length=255)
    attack_category_id: int = Field(ge=0, le=5)
    features: CoreFlow


def mount_inference(app, manager, store):
    controller = InferenceController(manager, store)

    @app.get("/api/model")
    def model():
        return controller.model()

    @app.post("/api/traffic/central-test")
    def save_central_test(
        request: Request,
        samples: Annotated[list[CentralTestSample], Body(min_length=1, max_length=50)],
    ):
        return controller.save_central_test(samples, request)
