"""Manage Windows Firewall rules owned by Flowwatch."""

import base64
import json
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from threading import Event, Lock, Thread
from time import time

from .firewall_log import format_drop_report


def epoch_ms():
    return int(time() * 1000)


class Firewall:
    def __init__(self, enabled=False):
        self.enabled = enabled and os.name == "nt"
        self.lock = Lock()
        self.stop_event = Event()
        self.worker = None
        self.log_reports = None

    def open_log(self, rule_id=None):
        log = self.run("find-log")
        rule = None
        if rule_id is not None:
            rule = next(
                (record for record in log["rules"] if record["id"] == rule_id), None
            )
            if rule is None:
                raise LookupError("This Flowwatch rule is no longer available.")
        if not log["loggingEnabled"]:
            raise RuntimeError(
                "Enable Log dropped packets in Windows Firewall before opening its log."
            )
        if not log["path"]:
            raise RuntimeError(
                "No readable Windows Firewall log was found. Check the log path and try again after a packet is dropped."
            )
        editor = Path(os.environ["SystemRoot"]) / "System32" / "notepad.exe"
        try:
            report = format_drop_report(Path(log["path"]), log["rules"], rule)
        except PermissionError as error:
            raise RuntimeError(
                "Flowwatch cannot read the Windows Firewall log. Restart the Flowwatch backend from PowerShell as Administrator."
            ) from error
        except ValueError as error:
            raise RuntimeError(str(error)) from error
        except OSError as error:
            raise RuntimeError(
                "Could not read the Windows Firewall log. Check that the log still exists and try again."
            ) from error
        try:
            with self.lock:
                if self.log_reports is None:
                    self.log_reports = TemporaryDirectory(
                        prefix="flowwatch-firewall-", ignore_cleanup_errors=True
                    )
                with NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.log_reports.name,
                    prefix="Firewall drops ",
                    suffix=".txt",
                    delete=False,
                ) as stream:
                    stream.write(report)
                    report_path = stream.name
        except OSError as error:
            raise RuntimeError(
                "Could not write the Windows Firewall summary to the temporary folder."
            ) from error
        try:
            os.startfile(
                editor,
                operation="runas",
                arguments=subprocess.list2cmdline([report_path]),
            )
        except OSError as error:
            if getattr(error, "winerror", None) == 1223:
                raise RuntimeError(
                    "Notepad was not opened because the Windows administrator prompt was canceled."
                ) from error
            raise RuntimeError(
                "Could not open the Windows Firewall log in Notepad."
            ) from error

    def start(self):
        if self.enabled:
            self.worker = Thread(target=self.sweep, daemon=True, name="firewall-expiry")
            self.worker.start()

    def stop(self):
        self.stop_event.set()
        with self.lock:
            if self.log_reports is not None:
                self.log_reports.cleanup()
                self.log_reports = None

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
        script = (
            Path(__file__).with_name("windows_firewall.ps1").read_text(encoding="utf-8")
        )
        command = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        executable = (
            Path(os.environ["SystemRoot"])
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        try:
            with self.lock:
                result = subprocess.run(
                    [
                        str(executable),
                        "-NoProfile",
                        "-NonInteractive",
                        "-EncodedCommand",
                        command,
                    ],
                    input=json.dumps({"action": action, **fields}),
                    capture_output=True,
                    encoding="utf-8",
                    timeout=20,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            if result.returncode:
                raise RuntimeError(
                    "Windows Firewall could not apply the request. Check administrator privileges, policy, and existing rules."
                )
            return json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            raise RuntimeError("Windows Firewall could not be reached.") from error
