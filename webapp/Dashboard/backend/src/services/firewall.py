"""Manage Windows Firewall rules owned by Flowwatch."""
import base64
import json
import os
from pathlib import Path
import subprocess
from threading import Event, Lock, Thread
from time import time


def epoch_ms():
    return int(time()*1000)


class Firewall:
    def __init__(self, enabled=False):
        self.enabled = enabled and os.name == "nt"
        self.lock = Lock()
        self.stop_event = Event()
        self.worker = None

    def start(self):
        if self.enabled:
            self.worker = Thread(target=self.sweep, daemon=True, name="firewall-expiry")
            self.worker.start()

    def stop(self):
        self.stop_event.set()

    def sweep(self):
        while not self.stop_event.is_set():
            try:
                self.run("expire", now=epoch_ms())
            except RuntimeError:
                pass
            self.stop_event.wait(15)

    def run(self, action, **fields):
        if not self.enabled:
            if action == "list":
                return {"writable": False, "rules": []}
            raise RuntimeError("Windows Firewall integration is disabled.")
        script = Path(__file__).with_name("windows_firewall.ps1").read_text(encoding="utf-8")
        command = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        executable = Path(os.environ["SystemRoot"])/"System32"/"WindowsPowerShell"/"v1.0"/"powershell.exe"
        try:
            with self.lock:
                result = subprocess.run(
                    [str(executable), "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
                    input=json.dumps({"action": action, **fields}), capture_output=True,
                    encoding="utf-8", timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
                )
            if result.returncode:
                raise RuntimeError("Windows Firewall could not apply the request. Check administrator privileges, policy, and existing rules.")
            return json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            raise RuntimeError("Windows Firewall could not be reached.") from error
