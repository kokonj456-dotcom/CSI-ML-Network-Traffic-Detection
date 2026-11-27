"""Input schemas for the Windows Firewall routes."""

from typing import Literal

from pydantic import BaseModel, Field


class BlockOptions(BaseModel):
    reason: str = Field(min_length=1, max_length=160)
    duration: Literal[15, 60, 1440]


class BlockTarget(BaseModel):
    ip: str = Field(max_length=45)
    flowId: str | None = Field(default=None, max_length=120)
    flowTime: int | None = None


class BlockRequest(BlockOptions):
    targets: list[BlockTarget] = Field(min_length=1, max_length=250)
