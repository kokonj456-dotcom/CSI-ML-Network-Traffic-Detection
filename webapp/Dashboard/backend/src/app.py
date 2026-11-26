"""Serve the Flowwatch frontend and local inference API."""
import argparse
from contextlib import asynccontextmanager
from os import environ
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from dotenv import dotenv_values
from starlette.middleware.trustedhost import TrustedHostMiddleware
from mysql.connector import Error as MySQLError
import uvicorn

from .routes.inference import mount_inference
from .routes.firewall import mount_firewall
from .routes.frontend import mount_frontend
from .routes.management import mount_management
from .config import DASHBOARD, DEFAULT_BUNDLE, MODEL_BACKUP_DIR, STATE_DIR
from .services.inference import Predictor
from .services.firewall import Firewall
from .services.live_capture import LiveCapture
from .services.model_management import Management
from .db.mysql_store import MySQLStore, mysql_settings


def create_app(bundle=DEFAULT_BUNDLE, state_dir=STATE_DIR):
    default_workspace = state_dir.resolve() == STATE_DIR.resolve()
    backup_dir = MODEL_BACKUP_DIR if default_workspace else state_dir/"model_backup"
    settings = mysql_settings() if default_workspace else None
    store = MySQLStore(settings) if settings else None
    manager = Management(state_dir, bundle, Predictor, backup_dir, store)
    config = {**dotenv_values(DASHBOARD/".env"), **environ} if default_workspace else {}
    live = LiveCapture(store, manager, config.get("FLOWWATCH_LIVE_INTERFACE"), config.get("FLOWWATCH_LIVE_IP"),
                       config.get("FLOWWATCH_LIVE_DIRECTION", "inbound"),
                       capture_https=config.get("FLOWWATCH_LIVE_HTTPS", "on").strip().lower() != "off",
                       settings_path=state_dir/"live_capture.json")
    firewall = Firewall(config.get("FLOWWATCH_WINDOWS_FIREWALL", "off").strip().lower() == "on")

    @asynccontextmanager
    async def lifespan(app):
        live.start()
        firewall.start()
        try:
            yield
        finally:
            live.stop()
            firewall.stop()

    app = FastAPI(title="Flowwatch CENTRAL inference", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.exception_handler(MySQLError)
    async def mysql_unavailable(request, error):
        return JSONResponse({"detail": "MySQL is unavailable or its schema has not been initialized."}, status_code=503)

    mount_management(app, manager)
    mount_inference(app, manager, store, live)
    mount_firewall(app, firewall, live.address)

    mount_frontend(app)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--port", type=int, default=8794)
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR)
    args = parser.parse_args()
    uvicorn.run(create_app(args.bundle, args.state_dir), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
