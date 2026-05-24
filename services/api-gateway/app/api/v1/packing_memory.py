"""Packing Memory RAG endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.services import packing_memory_service

router = APIRouter(prefix="/trips", tags=["Packing Memory"])


class PackingMemoryFeedbackRequest(BaseModel):
    feedback: str


@router.get("/{trip_id}/packing-memory")
async def get_trip_packing_memory(
    trip_id: UUID,
    user_id: CurrentUser,
    session: DbSession,
):
    """
    Retrieve the packing memory record saved for a specific trip.

    Returns the items packed, missing items, and any user feedback.
    """
    record = await packing_memory_service.get_trip_packing_memory(
        session, str(trip_id), user_id
    )
    if not record:
        raise NotFoundError("No packing memory found for this trip")
    return record


@router.post("/{trip_id}/packing-memory/feedback", status_code=status.HTTP_200_OK)
async def submit_packing_memory_feedback(
    trip_id: UUID,
    body: PackingMemoryFeedbackRequest,
    user_id: CurrentUser,
    session: DbSession,
):
    """Submit feedback on what worked or was missing from a past packing plan."""
    record = await packing_memory_service.get_trip_packing_memory(
        session, str(trip_id), user_id
    )
    if not record:
        raise NotFoundError("No packing memory found for this trip")

    result = await packing_memory_service.update_packing_memory_feedback(
        session, memory_id=record["id"], user_id=user_id, feedback=body.feedback
    )
    if not result:
        raise NotFoundError("Packing memory record not found")
    return result
