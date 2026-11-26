"""Public paths for the dashboard and its compiled assets."""
from fastapi.staticfiles import StaticFiles

from ..config import FRONTEND_BUILD
from ..controllers.frontend import frontend


def mount_frontend(app):
    app.mount("/assets", StaticFiles(directory=FRONTEND_BUILD / "assets", check_dir=False), name="frontend-assets")
    for path in ("/", "/index.html"):
        app.add_api_route(path, frontend, methods=["GET"], include_in_schema=False)
