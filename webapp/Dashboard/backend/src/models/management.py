"""Request schemas for model management."""

from typing import Literal

from pydantic import BaseModel, Field


class Report(BaseModel):
    flow: dict
    reason: str = Field(default="", max_length=1200)
    evidence: str = Field(default="", max_length=1200)


class Review(BaseModel):
    status: Literal["approved", "rejected"]
    note: str = Field(min_length=3, max_length=1200)


class Training(BaseModel):
    config: dict
    feedback_ids: list[str] = Field(default_factory=list, max_length=1000)


class Activation(BaseModel):
    version: str
