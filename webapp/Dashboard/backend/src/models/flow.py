"""Input schema for the CENTRAL predictor."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CoreFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration: float = Field(ge=0, allow_inf_nan=False)
    bytes_forward: float = Field(ge=0, allow_inf_nan=False)
    bytes_backward: float = Field(ge=0, allow_inf_nan=False)
    protocol: Literal["tcp", "udp", "icmp", "other"]
    service_group: Literal["dns", "ftp", "http", "https_ssl", "smtp", "ssh", "other"]
    conn_state_group: Literal["established", "no-reply", "reset", "other"]
