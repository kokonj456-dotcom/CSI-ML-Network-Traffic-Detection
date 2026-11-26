"""Handle firewall operations requested by the API."""
from ipaddress import ip_address
from uuid import uuid4

from fastapi import HTTPException

from ..services.firewall import epoch_ms


class FirewallController:
    def __init__(self, firewall, monitored_ip):
        self.firewall = firewall
        self.monitored_ip = monitored_ip

    @staticmethod
    def local_write(request):
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Submit firewall changes from the local Flowwatch dashboard.")

    def run(self, action, **fields):
        try:
            return self.firewall.run(action, **fields)
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error

    @staticmethod
    def reason_text(body):
        reason = body.reason.strip()
        if not reason:
            raise HTTPException(422, "Enter a reason for the block.")
        return reason

    def rules(self):
        return self.run("list") | {"connected": self.firewall.enabled}

    def add(self, body, request):
        self.local_write(request)
        now = epoch_ms()
        reason = self.reason_text(body)
        rules = {}
        for target in body.targets:
            try:
                address = ip_address(target.ip)
            except ValueError as error:
                raise HTTPException(422, "Enter a single IPv4 or IPv6 address.") from error
            ipv4 = getattr(address, "ipv4_mapped", None)
            address = ipv4 or address
            if address.is_loopback or address.is_unspecified or address.is_multicast or getattr(address, "scope_id", None) or str(address) in (self.monitored_ip, "255.255.255.255"):
                raise HTTPException(422, "This address cannot be used as a remote source IP.")
            ip = str(address)
            rules.setdefault(ip, {"id": uuid4().hex, "ip": ip, "reason": reason, "createdAt": now,
                                  "expiresAt": now+body.duration*60_000, "unblockedAt": None,
                                  "flowId": target.flowId, "flowTime": target.flowTime})
        return self.run("add", rules=list(rules.values()))

    def edit(self, identifier, body, request):
        self.local_write(request)
        return self.run("edit", id=identifier, reason=self.reason_text(body), expiresAt=epoch_ms()+body.duration*60_000)

    def unblock(self, identifier, request):
        self.local_write(request)
        return self.run("unblock", id=identifier, now=epoch_ms())
