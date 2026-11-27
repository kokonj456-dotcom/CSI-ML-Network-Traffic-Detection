"""HTTP endpoints for capture files."""

from fastapi import Query, Request

from ..controllers.captures import CaptureController


def mount_captures(app, manager, store):
    controller = CaptureController(manager, store)

    @app.post("/api/capture-uploads")
    async def upload_capture(
        request: Request, name: str = Query(min_length=1, max_length=180)
    ):
        return await controller.upload_capture(request, name)
