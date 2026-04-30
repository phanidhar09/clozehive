"""Kafka event envelope for worker processing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    event_version: int = 1
    request_id: UUID
    user_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "ai-worker"
    payload: dict[str, Any] = Field(default_factory=dict)

    def key(self) -> bytes:
        return str(self.request_id).encode("utf-8")

    def value(self) -> bytes:
        return self.model_dump_json().encode("utf-8")
