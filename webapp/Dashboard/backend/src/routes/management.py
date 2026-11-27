"""HTTP endpoints for feedback, training, and activation."""

from fastapi import Request

from ..models.management import Activation, Report, Review, Training
from ..controllers.management import ManagementController


def mount_management(app, manager):
    controller = ManagementController(manager)

    @app.get("/api/management")
    def management_overview():
        return controller.management_overview()

    @app.post("/api/management/feedback")
    def feedback(body: Report, request: Request):
        return controller.feedback(body, request)

    @app.post("/api/management/feedback/{identifier}")
    def review(identifier: str, body: Review, request: Request):
        return controller.review(identifier, body, request)

    @app.post("/api/management/jobs")
    def job(body: Training, request: Request):
        return controller.job(body, request)

    @app.post("/api/management/activate")
    def activate(body: Activation, request: Request):
        return controller.activate(body, request)
