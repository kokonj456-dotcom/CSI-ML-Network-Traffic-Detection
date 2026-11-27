"""Handle management operations requested by the API."""

from fastapi import HTTPException


class ManagementController:
    def __init__(self, manager):
        self.manager = manager

    @staticmethod
    def write(request):
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(
                403, "Submit changes from the local Flowwatch dashboard."
            )

    @staticmethod
    def perform(action):
        try:
            return action()
        except (ValueError, OSError, KeyError) as error:
            raise HTTPException(400, str(error)) from error

    def management_overview(self):
        return self.manager.overview()

    def feedback(self, body, request):
        self.write(request)
        return {"id": self.perform(lambda: self.manager.report(body))}

    def review(self, identifier, body, request):
        self.write(request)
        self.perform(lambda: self.manager.review(identifier, body))
        return {"ok": True}

    def job(self, body, request):
        self.write(request)
        return {"id": self.perform(lambda: self.manager.start(body))}

    def activate(self, body, request):
        self.write(request)
        self.perform(lambda: self.manager.activate(body))
        return {"ok": True}
