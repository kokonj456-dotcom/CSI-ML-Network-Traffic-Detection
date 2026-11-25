"""Loopback endpoints for Flowwatch-owned firewall rules."""
from ipaddress import ip_address
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from ..services.firewall import epoch_ms


class BlockOptions(BaseModel):
    reason: str = Field(min_length=1, max_length=160)
    duration: Literal[15, 60, 1440]


class BlockTarget(BaseModel):
    ip: str = Field(max_length=45)
    flowId: str | None = Field(default=None, max_length=120)
    flowTime: int | None = None


class BlockRequest(BlockOptions):
    targets: list[BlockTarget] = Field(min_length=1, max_length=250)


def mount_firewall(app, firewall, monitored_ip):
    def local_write(request):
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Submit firewall changes from the local Flowwatch dashboard.")

    def run(action, **fields):
        try:
            return firewall.run(action, **fields)
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error

    def reason_text(body):
        reason = body.reason.strip()
        if not reason:
            raise HTTPException(422, "Enter a reason for the block.")
        return reason

    @app.get("/api/firewall")
    def rules():
        return run("list") | {"connected": firewall.enabled}

    @app.post("/api/firewall")
    def add(body: BlockRequest, request: Request):
        local_write(request)
        now = epoch_ms()
        reason = reason_text(body)
        rules = {}
        for target in body.targets:
            try:
                address = ip_address(target.ip)
            except ValueError as error:
                raise HTTPException(422, "Enter a single IPv4 or IPv6 address.") from error
            ipv4 = getattr(address, "ipv4_mapped", None)
            address = ipv4 or address
            if address.is_loopback or address.is_unspecified or address.is_multicast or getattr(address, "scope_id", None) or str(address) in (monitored_ip, "255.255.255.255"):
                raise HTTPException(422, "This address cannot be used as a remote source IP.")
            ip = str(address)
            rules.setdefault(ip, {"id": uuid4().hex, "ip": ip, "reason": reason, "createdAt": now,
                                  "expiresAt": now+body.duration*60_000, "unblockedAt": None,
                                  "flowId": target.flowId, "flowTime": target.flowTime})
        return run("add", rules=list(rules.values()))

    @app.patch("/api/firewall/{identifier}")
    def edit(identifier: str, body: BlockOptions, request: Request):
        local_write(request)
        return run("edit", id=identifier, reason=reason_text(body), expiresAt=epoch_ms()+body.duration*60_000)

    @app.delete("/api/firewall/{identifier}")
    def unblock(identifier: str, request: Request):
        local_write(request)
        return run("unblock", id=identifier, now=epoch_ms())
