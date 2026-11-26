"""Serve the local Traffic Replay console and its sample HTTP endpoint."""

from argparse import ArgumentParser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import csv
import json
import socket
from pathlib import Path
from ipaddress import IPv4Address
from random import choice, sample
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parent
TEST_SPLIT = ROOT.parents[1] / "data-pipeline" / "CENTRAL" / "output" / "splits" / "test"
FEATURE_FIELDS = ("duration", "protocol", "bytes_forward", "bytes_backward",
                  "service_group", "conn_state_group")


@lru_cache(maxsize=1)
def normal_test_records():
    with (TEST_SPLIT / "labels.csv").open(encoding="utf-8-sig", newline="") as stream:
        normal_ids = {row["record_id"] for row in csv.DictReader(stream) if row["label_binary"] == "0"}
    with (TEST_SPLIT / "features.csv").open(encoding="utf-8-sig", newline="") as stream:
        records = [
            {"record_id": row["record_id"], "features": {key: row[key] for key in FEATURE_FIELDS}}
            for row in csv.DictReader(stream) if row["record_id"] in normal_ids
        ]
    if not records:
        raise ValueError("No matching Normal records in CENTRAL Test.")
    return records


CLASS_NAMES = ("Normal", "Denial of Service (DoS)", "Reconnaissance & Probing",
               "Exploits & PrivEsc", "Credential Abuse (R2L)", "Malware, C2 & Botnet")


def evaluate_demo(attack_class=None):
    groups = [[] for _ in CLASS_NAMES]
    with (TEST_SPLIT / "labels.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            groups[int(row["attack_category_id"])].append(row["record_id"])
    selected = {
        record_id: category
        for category, group in enumerate(groups)
        if attack_class is None or category == attack_class
        for record_id in sample(group, 25 if category == 0 else 5)
    }
    with (TEST_SPLIT / "features.csv").open(encoding="utf-8-sig", newline="") as stream:
        features = {row["record_id"]: {key: row[key] for key in FEATURE_FIELDS}
                    for row in csv.DictReader(stream) if row["record_id"] in selected}
    samples = [{"record_id": key, "attack_category_id": category, "features": features[key]}
               for key, category in selected.items()]
    request = Request("http://127.0.0.1:8794/api/traffic/central-test",
                      data=json.dumps(samples).encode(),
                      headers={"Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=20) as response:
        saved = json.load(response)
    rows = []
    for (record_id, category), result, identifiers in zip(
        selected.items(), saved["predictions"], saved["records"], strict=True
    ):
        scored = result["status"] == "scored"
        predicted = "Not scored"
        if scored:
            predicted = "Attack category unclear" if result.get("category_unclear") else CLASS_NAMES[result["class_id"]]
        rows.append({"record_id": record_id, "actual": CLASS_NAMES[category],
                     "predicted": predicted, "score": result.get("binary_score"),
                     "threshold": result.get("threshold"), "flagged": result.get("flagged"),
                     "model": result.get("model_id"), **identifiers})
    return rows


def discover_capture_address():
    """Prefer Flowwatch's selected IPv4 so replay requests traverse that address."""
    try:
        request = Request("http://127.0.0.1:8794/api/traffic/live")
        with build_opener(ProxyHandler({})).open(request, timeout=2) as response:
            address = json.load(response).get("address")
        parsed = IPv4Address(address)
        if not parsed.is_loopback and not parsed.is_unspecified:
            return str(parsed)
    except (OSError, ValueError, TypeError):
        pass

    # The UDP connect only asks Windows which local interface it would route through;
    # it does not send a packet to the documentation-only destination.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_probe:
            route_probe.connect(("192.0.2.1", 9))
            address = IPv4Address(route_probe.getsockname()[0])
        if not address.is_loopback and not address.is_unspecified:
            return str(address)
    except OSError:
        pass
    return "127.0.0.1"


class ReplayHandler(BaseHTTPRequestHandler):
    # Close after each response so successive samples form distinct connections.
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        status = 200
        if self.path == "/":
            content = (ROOT / "index.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        elif self.path == "/sample":
            content_type = "application/json"
            try:
                result = {"service": "traffic-replay", "status": "ok", "dataset": "CENTRAL Test",
                          "label": "Normal", **choice(normal_test_records())}
            except (OSError, ValueError, KeyError, csv.Error):
                status = 503
                result = {"error": "อ่านตัวอย่าง Normal จาก CENTRAL Test ไม่ได้"}
            content = json.dumps(result).encode("utf-8")
        else:
            self.send_error(404)
            return

        self.send_content(status, content_type, content)

    def do_POST(self):
        status = 200
        if self.headers.get("Origin") not in (None, f"http://{self.headers.get('Host')}"):
            self.send_error(403)
            return
        if urlsplit(self.path).path == "/central-demo":
            content_type = "application/json"
            classes = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get("class")
            if classes is not None and (len(classes) != 1 or classes[0] not in {"1", "2", "3", "4", "5"}):
                status, result = 400, {"error": "กรุณาเลือกคลาสโจมตี 1–5"}
            else:
                try:
                    result = {"rows": evaluate_demo(int(classes[0]) if classes else None)}
                except (OSError, ValueError, KeyError, IndexError, csv.Error):
                    status = 503
                    result = {"error": "ประเมินไม่ได้ กรุณาตรวจว่า CENTRAL Test พร้อมใช้งานและ Flowwatch เปิดอยู่"}
            content = json.dumps(result).encode("utf-8")
        else:
            self.send_error(404)
            return

        self.send_content(status, content_type, content)

    def send_content(self, status, content_type, content):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        if self.path == "/sample":
            source_ip, source_port = self.client_address
            self.send_header("X-Replay-Source", f"{source_ip}:{source_port}")
        self.end_headers()
        self.wfile.write(content)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="auto",
                        help="IPv4 address to bind; auto uses Flowwatch's capture address")
    args = parser.parse_args()
    host = discover_capture_address() if args.host == "auto" else str(IPv4Address(args.host))
    with ThreadingHTTPServer((host, args.port), ReplayHandler) as server:
        print(f"Traffic Replay: http://{host}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
