"""Preview or clear Flowwatch MySQL records and remove inactive model backups."""

import argparse
import re
import shutil
import socket
import sqlite3
from contextlib import closing

from backend.src.config import MODEL_BACKUP_DIR, STATE_DIR
from backend.src.db.mysql_store import MySQLStore, mysql_settings
from backend.src.services.model_registry import ModelRegistry


# Delete children before their foreign-key parents.
TABLES = (
    "false_positive_feedback", "alerts", "predictions",
    "flow_protocol_events", "traffic_flows", "capture_files",
)
VERSION = re.compile(r"[0-9a-f]{32}")


def checked_directory(path, parent):
    resolved = path.resolve(strict=True)
    if (not path.is_dir() or path.is_symlink() or path.is_junction()
            or resolved.parent != parent or resolved != path):
        raise RuntimeError(f"Unsafe directory: {path}")
    return resolved


def model_plan():
    backup = checked_directory(MODEL_BACKUP_DIR, MODEL_BACKUP_DIR.parent.resolve())
    registry = ModelRegistry(backup, None)
    active = registry.active_path.read_text(encoding="utf-8").strip()
    kept = {checked_directory(registry.bundle_path(version), backup)
            for version in ("baseline", active)}
    if any(not (path / "manifest.json").is_file() for path in kept):
        raise RuntimeError("Cannot verify the active and baseline bundles.")
    obsolete = {}
    for entry in sorted(backup.iterdir()):
        if not (entry.is_dir() or entry.is_symlink() or entry.is_junction()):
            continue
        folder = checked_directory(entry, backup)
        if folder in kept:
            continue
        marker = folder / ".registry-version"
        version = (marker.read_text(encoding="utf-8").strip() if marker.is_file()
                   else folder.name.rsplit("__", 1)[-1])
        if not VERSION.fullmatch(version) or version == active:
            raise RuntimeError(f"Cannot identify model backup safely: {folder}")
        obsolete[folder] = version
    return kept, obsolete


def require_stopped(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Stop Flowwatch on port {port} before applying cleanup.")


def cleanup(apply, port):
    if apply:
        require_stopped(port)
    kept, obsolete = model_plan()
    state = STATE_DIR.resolve(strict=True)
    job_dirs = []
    versions = sorted(set(obsolete.values()))
    jobs = state / "jobs"
    for version in versions:
        path = jobs / version
        if path.exists() or path.is_symlink() or path.is_junction():
            checked_directory(jobs, state)
            job_dirs.append(checked_directory(path, jobs))

    settings = mysql_settings()
    if settings is None:
        raise RuntimeError("Configure Flowwatch MySQL in Dashboard/.env first.")
    store = MySQLStore(settings)
    database = state / "management.sqlite3"
    with closing(sqlite3.connect(database.as_uri() + "?mode=" + ("rw" if apply else "ro"), uri=True)) as management:
        if management.execute("SELECT 1 FROM jobs WHERE status = 'running' LIMIT 1").fetchone():
            raise RuntimeError("Wait for training jobs to finish before cleanup.")
        print(f"MySQL database: {settings['database']}")
        with store.transaction() as cursor:
            for table in TABLES:
                cursor.execute(f"SELECT COUNT(*) AS total FROM `{table}`")
                print(f"  {table}: {cursor.fetchone()['total']} rows")
        for path in sorted(kept):
            print(f"Keep: {path.name}")
        for path in obsolete:
            print(f"Remove: {path.name}")
        if not apply:
            print("Preview only. Run again with --apply to delete.")
            return

        with store.transaction() as cursor:
            for table in TABLES:
                cursor.execute(f"DELETE FROM `{table}`")
        with store.transaction() as cursor:
            for table in TABLES:
                cursor.execute(f"SELECT COUNT(*) AS total FROM `{table}`")
                if cursor.fetchone()["total"]:
                    raise RuntimeError(f"{table} is not empty; check for another running writer.")

        # Remove registry job entries before deleting bundles to prevent restoration at startup.
        with management:
            management.executemany("DELETE FROM jobs WHERE id = ?", [(version,) for version in versions])
        for path in [*obsolete, *job_dirs]:
            shutil.rmtree(checked_directory(path, path.parent))
        print("Cleanup complete. All six MySQL tables are empty.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete the listed records and backups.")
    parser.add_argument("--port", type=int, default=8794, help="Flowwatch backend port.")
    args = parser.parse_args()
    try:
        cleanup(args.apply, args.port)
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Cleanup stopped: {error}\n")


if __name__ == "__main__":
    main()
