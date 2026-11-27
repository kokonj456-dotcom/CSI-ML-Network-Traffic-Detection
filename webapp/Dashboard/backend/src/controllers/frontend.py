"""Serve the built dashboard entry document."""

from fastapi import HTTPException
from fastapi.responses import FileResponse

from ..config import FRONTEND_BUILD


def frontend():
    index = FRONTEND_BUILD / "index.html"
    if not index.is_file():
        raise HTTPException(
            503,
            "Build the React frontend with npm ci and npm run build in the frontend folder.",
        )
    return FileResponse(index, headers={"Cache-Control": "no-store"})
