"""
Trip routes — /api/v1/trips/*
MVP: Create, list, get, update trips for travel packing
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.closet import ClosetItem
from app.schemas.trips import CreateTripResponse, PackingPlanResponse, SavePlannerResponse, TripCreate, TripResponse, TripListResponse
from app.services import ai_client, packing_service
from app.services.style_profile_context import load_merged_user_profile_for_ai
from app.services.trips_service import TripsService


router = APIRouter(prefix="/trips", tags=["Trips"])
logger = get_logger("trips")


async def _generate_trip_packing(
    session: AsyncSession,
    user_id: UUID,
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[dict[str, Any]],
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Prefer ai-agent (LangChain + MCP) so LangSmith traces trip packing; fall back to
    in-gateway packing_service if the agent is unavailable.

    Hard wall-clock cap of 50 s so the HTTP handler never times out on the client side.
    """
    prof = await load_merged_user_profile_for_ai(session, user_id, None)

    async def _run() -> dict[str, Any]:
        try:
            return await ai_client.generate_packing_list(
                destination,
                start_date,
                end_date,
                purpose,
                closet_items,
                notes=notes,
                user_style_profile=prof,
            )
        except Exception as exc:
            logger.warning(
                "trip_packing_ai_agent_fallback",
                error=str(exc),
                destination=destination,
            )
            return await packing_service.generate_packing_list(
                destination,
                start_date,
                end_date,
                purpose,
                closet_items,
                notes=notes,
                user_style_profile=prof,
            )

    try:
        return await asyncio.wait_for(_run(), timeout=50.0)
    except asyncio.TimeoutError:
        logger.warning("trip_packing_total_timeout", destination=destination)
        # Last-resort synchronous fallback — always returns something
        return await packing_service.generate_packing_list(
            destination,
            start_date,
            end_date,
            purpose,
            closet_items,
            notes=notes,
            user_style_profile=prof,
        )


def _get_svc(session: AsyncSession) -> TripsService:
    return TripsService(session)


# ── List / Get ────────────────────────────────────────────────────────────────

@router.get("/", response_model=TripListResponse)
async def list_trips(
    user_id: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    return await svc.list_trips(UUID(user_id))


@router.get("/saved", response_model=TripListResponse)
async def list_saved_trips(
    user_id: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    return await svc.list_saved_trips(UUID(user_id))


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    return await svc.get_trip(trip_id, UUID(user_id))


@router.get("/{trip_id}/packing-list")
async def get_packing_list(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    trip = await svc.get_trip(trip_id, UUID(user_id))
    result = await session.execute(
        select(ClosetItem)
        .where(ClosetItem.user_id == UUID(user_id), ClosetItem.is_archived == False)  # noqa: E712
        .order_by(ClosetItem.wear_count.desc(), ClosetItem.created_at.desc())
        .limit(200)
    )
    closet_items = [
        {
            "id": str(item.id),
            "name": item.name,
            "category": item.category,
            "color": item.color or "",
            "brand": item.brand or "",
            "fabric": item.fabric or "",
            "size": item.size or "",
            "season": item.season or "",
            "occasion": item.occasion or [],
            "notes": item.notes or "",
        }
        for item in result.scalars().all()
    ]
    return await _generate_trip_packing(
        session,
        UUID(user_id),
        trip.destination,
        trip.start_date.isoformat(),
        trip.end_date.isoformat(),
        trip.purpose,
        closet_items,
        notes=trip.notes,
    )


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=CreateTripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    user_id: CurrentUser,
    body: TripCreate,
    session: AsyncSession = Depends(get_session),
):
    if body.end_date <= body.start_date:
        raise BadRequestError("end_date must be after start_date")
    svc = _get_svc(session)
    trip = await svc.create_trip(UUID(user_id), body)

    # Fetch closet items for packing generation
    result = await session.execute(
        select(ClosetItem)
        .where(ClosetItem.user_id == UUID(user_id), ClosetItem.is_archived == False)  # noqa: E712
        .order_by(ClosetItem.wear_count.desc(), ClosetItem.created_at.desc())
        .limit(200)
    )
    closet_items = [
        {
            "id": str(item.id),
            "name": item.name,
            "category": item.category,
            "color": item.color or "",
            "brand": item.brand or "",
            "fabric": item.fabric or "",
            "size": item.size or "",
            "season": item.season or "",
            "occasion": item.occasion or [],
            "notes": item.notes or "",
        }
        for item in result.scalars().all()
    ]

    packing_plan = None
    packing_error = None
    try:
        packing_result = await _generate_trip_packing(
            session,
            UUID(user_id),
            trip.destination,
            trip.start_date.isoformat(),
            trip.end_date.isoformat(),
            trip.purpose,
            closet_items,
            notes=trip.notes,
        )
        packing_plan = await svc.save_packing_plan(trip.id, UUID(user_id), packing_result)
    except Exception as exc:
        packing_error = str(exc)

    return CreateTripResponse(trip=trip, packing_plan=packing_plan, packing_error=packing_error)


# ── Packing plan ─────────────────────────────────────────────────────────────

@router.get("/{trip_id}/packing-plan", response_model=PackingPlanResponse)
async def get_packing_plan(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    plan = await svc.get_packing_plan(trip_id, UUID(user_id))
    if not plan:
        raise NotFoundError(f"No packing plan found for trip {trip_id}")
    return plan


# ── Save planner ─────────────────────────────────────────────────────────────

@router.post("/{trip_id}/save-planner", response_model=SavePlannerResponse)
async def save_planner(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    return await svc.mark_as_saved(trip_id, UUID(user_id))


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{trip_id}", response_model=TripResponse)
async def update_trip(
    user_id: CurrentUser,
    trip_id: UUID,
    body: TripCreate,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    return await svc.update_trip(trip_id, UUID(user_id), body)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    await svc.delete_trip(trip_id, UUID(user_id))
