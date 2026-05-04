"""Shared event envelopes for Kafka messages."""

from __future__ import annotations

from datetime import timezone, datetime
from typing import Optional, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    event_version: int = 1
    request_id: UUID
    user_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "api-gateway"
    payload: dict[str, Any] = Field(default_factory=dict)

    def kafka_key(self) -> bytes:
        return str(self.request_id).encode("utf-8")

    def kafka_value(self) -> bytes:
        return self.model_dump_json().encode("utf-8")


class AsyncAcceptedResponse(BaseModel):
    status: str = "accepted"
    request_id: UUID
    event_type: str
    message: str
