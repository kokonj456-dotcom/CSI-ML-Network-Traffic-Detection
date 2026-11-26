"""Convert between storage timestamps and API timestamps."""
from datetime import datetime, timezone


def utc_time(epoch_seconds):
    return datetime.fromtimestamp(epoch_seconds, timezone.utc).replace(tzinfo=None)


def wire_time(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value is not None else None
