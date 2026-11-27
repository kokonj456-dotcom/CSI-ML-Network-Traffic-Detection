"""Workspace paths and public static assets."""

import os
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parents[3]
ROOT = DASHBOARD.parents[1]
FRONTEND_BUILD = DASHBOARD / "frontend" / "dist"
PIPELINE = ROOT / "data-pipeline"
CENTRAL_SPLITS = PIPELINE / "CENTRAL" / "output" / "splits"
DEFAULT_BUNDLE = CENTRAL_SPLITS.parent / "flowwatch_bundle"
CAPTURES = Path(
    os.environ.get("FLOWWATCH_CAPTURE_DIR", DASHBOARD / "backend" / "captures")
).resolve()
STATE_DIR = ROOT / ".flowwatch"
MODEL_BACKUP_DIR = DASHBOARD / "backend" / "model_backup"
TRAINER = ROOT / "model" / "xgboost" / "train_flowwatch.py"


def capture_files():
    return sorted(path.name for path in CAPTURES.glob("*.pcap") if path.is_file())
