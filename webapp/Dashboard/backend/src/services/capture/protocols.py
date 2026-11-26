"""DNS, HTTP and TLS observations and service hints."""
import re

SERVICES = {20:"ftp",21:"ftp",22:"ssh",25:"smtp",53:"dns",80:"http",443:"https_ssl",8080:"http",8443:"https_ssl"}
HTTP_LINE = re.compile(rb"(?:(GET|HEAD|POST|PUT|DELETE|CONNECT|OPTIONS|TRACE|PATCH) [^\r\n ]+ HTTP/1\.[01]|HTTP/1\.[01] [1-5]\d\d(?: [^\r\n]*)?)\r?\n")


def web_observation(flow):
    if flow["dns_events"]:
        return {"label": "DNS", "basis": "Decoded DNS"}
    ports = {flow["src"][1], flow["dst"][1]}
    if flow["http"]:
        return {"label": "HTTP", "basis": "Observed HTTP/1.x request or response line"}
    if flow["tls"]:
        return {"label": "HTTPS/TLS" if ports & {443, 8443} else "TLS", "basis": "Observed TLS handshake header"}
    if flow["protocol"] == "udp" and 443 in ports:
        return {"label": "QUIC?", "basis": "UDP port 443. QUIC is possible."}
    if flow["protocol"] == "tcp" and ports & {443, 8443}:
        return {"label": "HTTPS/TLS", "basis": "TCP port hint"}
    if flow["protocol"] == "tcp" and ports & {80, 8080}:
        return {"label": "HTTP", "basis": "TCP port hint"}
    return None
