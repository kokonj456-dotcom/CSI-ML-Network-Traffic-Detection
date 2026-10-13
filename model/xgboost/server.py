"""
Lightweight Web Server for XGBoost Dashboard
Serves dashboard.html, lists backups from model/xgboost/backup/,
provides run details JSON, and executes new training runs on demand.
"""

import http.server
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1]
BACKUP_DIR = BASE_DIR / "backup"
DASHBOARD_HTML = BASE_DIR / "dashboard.html"


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(DASHBOARD_HTML, "rb") as f:
                self.wfile.write(f.read())
            return

        elif path == "/api/backups":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            backups = []
            if BACKUP_DIR.exists():
                for entry in sorted(BACKUP_DIR.iterdir(), reverse=True):
                    if not entry.is_dir(): continue
                    json_file = entry / "evaluation_results.json"
                    if not json_file.exists(): continue

                    try:
                        with open(json_file) as jf:
                            jdata = json.load(jf)
                            acc = jdata.get("kddtest_metrics", {}).get("accuracy")
                            mode = jdata.get("mode", "binary")
                            ts = jdata.get("timestamp", entry.name)

                            backups.append({
                                "name": entry.name,
                                "mode": mode,
                                "timestamp": ts,
                                "accuracy": acc,
                                "has_model": (entry / "xgboost_model.joblib").exists()
                            })
                    except Exception:
                        pass

            self.wfile.write(json.dumps({"backups": backups}).encode("utf-8"))
            return

        elif path == "/api/run-details":
            params = urllib.parse.parse_qs(parsed.query)
            run_name = params.get("run", [None])[0]

            if not run_name:
                self.send_error(400, "Missing run parameter")
                return

            target_json = BACKUP_DIR / run_name / "evaluation_results.json"
            if not target_json.exists():
                self.send_error(404, "Run not found")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            with open(target_json, "rb") as f:
                self.wfile.write(f.read())
            return

        # Serve static images/files from backup folder if requested
        elif path.startswith("/backup/"):
            rel_path = path[len("/backup/"):]
            file_path = BACKUP_DIR / rel_path
            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                if file_path.suffix == ".png":
                    self.send_header("Content-Type", "image/png")
                elif file_path.suffix == ".json":
                    self.send_header("Content-Type", "application/json")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/train":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            params = json.loads(body.decode("utf-8")) if body else {}

            mode = params.get("mode", "binary")
            n_estimators = str(params.get("n_estimators", 150))
            max_depth = str(params.get("max_depth", 6))
            lr = str(params.get("learning_rate", 0.1))
            cv_folds = str(params.get("cv_folds", 5))
            subsample = str(params.get("subsample", 0.8))
            colsample = str(params.get("colsample_bytree", 0.8))

            cmd = [
                sys.executable,
                str(BASE_DIR / "train.py"),
                "--mode", mode,
                "--n_estimators", n_estimators,
                "--max_depth", max_depth,
                "--learning_rate", lr,
                "--cv_folds", cv_folds,
                "--subsample", subsample,
                "--colsample_bytree", colsample,
            ]

            print(f"Executing: {' '.join(cmd)}")
            proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)

            if proc.returncode == 0:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "success",
                    "message": "Training completed and backed up successfully."
                }).encode("utf-8"))
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "error",
                    "message": proc.stderr or proc.stdout
                }).encode("utf-8"))
            return

        self.send_error(404, "Not Found")


import socketserver

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_server(port=PORT):
    server_address = ("", port)
    httpd = ThreadedHTTPServer(server_address, DashboardHandler)
    print(f"XGBoost Dashboard server running at: http://localhost:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_server(port)

