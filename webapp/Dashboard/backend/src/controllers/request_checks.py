"""Shared checks for saved traffic and local writes."""
from fastapi import HTTPException


class SavedTrafficController:
    def __init__(self, store):
        self.store = store

    def require_store(self):
        if self.store is None:
            raise HTTPException(503, "Configure MySQL to use saved traffic.")
        return self.store

    @staticmethod
    def require_local_write(request):
        if request.headers.get("origin") not in (None, str(request.base_url).rstrip("/")):
            raise HTTPException(403, "Submit changes from the local Flowwatch dashboard.")
