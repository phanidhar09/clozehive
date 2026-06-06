"""Async AI jobs — enqueue heavy work to the ai-worker and poll for results.

These endpoints keep the request/response cycle fast: instead of blocking on a
slow AI call, the gateway enqueues an ARQ job (handled by the ai-worker over
Redis) and returns a ``request_id`` immediately. Clients poll
``GET /ai/jobs/{request_id}`` until status is ``completed`` or ``failed``.

The worker writes results back to the ``ai_requests`` table, which is the source
of truth this router reads from.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.core.task_queue import (
    TASK_GENERATE_OUTFIT,
    TASK_GENERATE_PACKING,
    enqueue_ai_job,
)
from sqlalchemy import text

router = APIRouter(prefix="/ai/jobs", tags=["AI Jobs"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class OutfitJobRequest(BaseModel):
    """Free-form payload forwarded to the ai-agent's outfit generator."""

    occasion: str = Field(..., max_length=200)
    weather: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {"occasion": self.occasion, "weather": self.weather, "notes": self.notes}
        payload.update(self.extra)
        return payload


class PackingJobRequest(BaseModel):
    """Free-form payload forwarded to the ai-agent's packing generator."""

    destination: str = Field(..., max_length=200)
    start_date: Optional[str] = Field(default=None, max_length=40)
    end_date: Optional[str] = Field(default=None, max_length=40)
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "destination": self.destination,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }
        payload.update(self.extra)
        return payload


class JobAccepted(BaseModel):
    request_id: UUID
    status: str = "accepted"


class JobStatus(BaseModel):
    request_id: UUID
    request_type: str
    status: str
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/outfit", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_outfit(body: OutfitJobRequest, user_id: CurrentUser, session: DbSession) -> JobAccepted:
    request_id = await enqueue_ai_job(
        session,
        user_id=UUID(user_id),
        request_type="outfit",
        task_name=TASK_GENERATE_OUTFIT,
        task_args=[body.to_payload()],
        input_payload=body.to_payload(),
    )
    return JobAccepted(request_id=request_id)


@router.post("/packing", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_packing(body: PackingJobRequest, user_id: CurrentUser, session: DbSession) -> JobAccepted:
    request_id = await enqueue_ai_job(
        session,
        user_id=UUID(user_id),
        request_type="packing",
        task_name=TASK_GENERATE_PACKING,
        task_args=[body.to_payload()],
        input_payload=body.to_payload(),
    )
    return JobAccepted(request_id=request_id)


@router.get("/{request_id}", response_model=JobStatus)
async def get_job(request_id: UUID, user_id: CurrentUser, session: DbSession) -> JobStatus:
    """Poll a previously enqueued job. Scoped to the requesting user."""
    row = (
        await session.execute(
            text(
                """
                SELECT request_type, status, result_payload, error_message
                FROM ai_requests
                WHERE id = :id AND user_id = :user_id
                """
            ),
            {"id": request_id, "user_id": UUID(user_id)},
        )
    ).first()

    if row is None:
        raise NotFoundError("Job not found")

    result = row.result_payload
    if isinstance(result, str):  # asyncpg may hand JSONB back as a string
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            result = None

    return JobStatus(
        request_id=request_id,
        request_type=row.request_type,
        status=row.status,
        result=result,
        error=row.error_message,
    )
