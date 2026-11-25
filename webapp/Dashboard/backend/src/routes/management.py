"""HTTP endpoints for feedback, training, and activation."""
from fastapi import HTTPException, Request

from ..models.management import Activation, Report, Review, Training


def mount_management(app, manager):
    def write(request):
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403,"Submit changes from the local Flowwatch dashboard.")

    def perform(action):
        try:
            return action()
        except (ValueError, OSError, KeyError) as error:
            raise HTTPException(400,str(error)) from error

    @app.get("/api/management")
    def management_overview():
        return manager.overview()

    @app.post("/api/management/feedback")
    def feedback(body: Report, request: Request):
        write(request)
        return {"id":perform(lambda:manager.report(body))}

    @app.post("/api/management/feedback/{identifier}")
    def review(identifier: str, body: Review, request: Request):
        write(request)
        perform(lambda:manager.review(identifier,body))
        return {"ok":True}

    @app.post("/api/management/jobs")
    def job(body: Training, request: Request):
        write(request)
        return {"id":perform(lambda:manager.start(body))}

    @app.post("/api/management/activate")
    def activate(body: Activation, request: Request):
        write(request)
        perform(lambda:manager.activate(body))
        return {"ok":True}

