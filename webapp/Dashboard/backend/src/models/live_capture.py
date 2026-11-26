"""Input schema for live capture capacity settings."""
from pydantic import BaseModel, Field


class LiveCaptureSettings(BaseModel):
    max_flows_per_second: int = Field(ge=0, le=100000)
    packet_queue_capacity: int = Field(ge=64, le=262144)
    flow_queue_capacity: int = Field(ge=64, le=131072)
