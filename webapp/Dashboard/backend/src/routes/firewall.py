"""Loopback endpoints for Flowwatch-owned firewall rules."""
from fastapi import Request

from ..models.firewall import BlockOptions, BlockRequest
from ..controllers.firewall import FirewallController


def mount_firewall(app, firewall, monitored_ip):
    controller = FirewallController(firewall, monitored_ip)

    @app.get("/api/firewall")
    def rules():
        return controller.rules()

    @app.post("/api/firewall")
    def add(body: BlockRequest, request: Request):
        return controller.add(body, request)

    @app.patch("/api/firewall/{identifier}")
    def edit(identifier: str, body: BlockOptions, request: Request):
        return controller.edit(identifier, body, request)

    @app.delete("/api/firewall/{identifier}")
    def unblock(identifier: str, request: Request):
        return controller.unblock(identifier, request)
