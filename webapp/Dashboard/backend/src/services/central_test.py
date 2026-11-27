"""Prepare offline CENTRAL Test records for persistence."""

from time import time

from fastapi import HTTPException


def build_central_test_records(samples):
    now = time()
    records = []
    for sample in samples:
        raw = sample.features.model_dump()
        if (
            raw["duration"] > 31536000
            or max(raw["bytes_forward"], raw["bytes_backward"]) >= 2**64
        ):
            raise HTTPException(422, "CENTRAL flow values exceed storage limits.")
        records.append(
            {
                "raw": raw,
                "started_at": now - raw["duration"],
                "ended_at": now,
                "src": None,
                "dst": None,
                "sport": None,
                "dport": None,
                "packets_forward": 0,
                "packets_backward": 0,
                "frames": [],
                "protocol_events": [],
                "protocol_observation": None,
                "dataset": {
                    "record_id": sample.record_id,
                    "attack_category_id": sample.attack_category_id,
                },
            }
        )
    return records
