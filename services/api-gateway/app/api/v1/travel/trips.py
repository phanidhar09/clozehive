"""
Trip routes — /api/v1/trips/*
Activity-aware travel packing planner with bag-size optimization.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.identity.services.style_profile_context import load_merged_user_profile_for_ai
from app.api.v1.intelligence.services.fashion_rag_service import get_fashion_context_for_prompt
from app.api.v1.intelligence.services.purchase_gap_service import detect_and_save_gaps
from app.api.v1.travel.schemas.trips import (
    AddActivitiesRequest,
    ChecklistUpdateRequest,
    CreateTripResponse,
    PackingPlanResponse,
    SavePlannerResponse,
    TripCreate,
    TripListResponse,
    TripResponse,
)
from app.api.v1.travel.services import packing_service
from app.api.v1.travel.services.packing_memory_service import get_packing_memory_for_prompt, save_packing_memory
from app.api.v1.travel.services.trips_service import TripsService
from app.core.deps import CurrentUser
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.closet import ClosetItem

router = APIRouter(prefix="/trips", tags=["Trips"])
logger = get_logger("trips")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_svc(session: AsyncSession) -> TripsService:
    return TripsService(session)


async def _fetch_closet_items(session: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    result = await session.execute(
        select(ClosetItem)
        .where(ClosetItem.user_id == user_id, ClosetItem.is_archived == False)  # noqa: E712
        .order_by(ClosetItem.wear_count.desc(), ClosetItem.created_at.desc())
        .limit(200)
    )
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "category": item.category,
            "color": item.color or "",
            "brand": item.brand or "",
            "fabric": item.fabric or "",
            "pattern": getattr(item, "pattern", "") or "",
            "fit": item.fit or "",
            "size": item.size or "",
            "season": item.season or "",
            "occasion": item.occasion or [],
            "notes": item.notes or "",
            "image_url": item.image_url or "",
        }
        for item in result.scalars().all()
    ]


async def _build_packing_rag_context(
    session: Any,
    user_id: UUID,
    destination: str,
    purpose: str,
    activities: list[dict[str, Any]] | None = None,
    weather_summary: dict[str, Any] | None = None,
) -> str | None:
    parts: list[str] = []
    try:
        query = f"{purpose} trip packing {destination}"
        if activities:
            acts = ", ".join(a.get("name", "") for a in activities[:4] if a.get("name"))
            if acts:
                query += f" activities: {acts}"
        fashion_ctx = await get_fashion_context_for_prompt(session, query, limit=2)
        if fashion_ctx:
            parts.append(fashion_ctx)
    except Exception as exc:
        logger.warning("fashion_context_unavailable", error=str(exc))
    try:
        memory_ctx = await get_packing_memory_for_prompt(
            session, str(user_id), destination, purpose, weather_summary, limit=2
        )
        if memory_ctx:
            parts.append(memory_ctx)
    except Exception as exc:
        logger.warning("packing_memory_unavailable", error=str(exc))
    return "\n\n".join(parts) or None


async def _generate_trip_packing(
    session: AsyncSession,
    user_id: UUID,
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[dict[str, Any]],
    notes: str | None = None,
    activities: list[dict[str, Any]] | None = None,
    trip_style: str | None = None,
    bag_size: str | None = None,
    rag_context: str | None = None,
) -> dict[str, Any]:
    """
    Generate packing plan via the in-gateway packing_service — the single,
    full-featured packing implementation (RAG-grounded, honours activities /
    trip_style / bag_size, returns a graceful mock on AI failure). 50s hard
    timeout; packing_service supplies its own per-step fallbacks within it.

    (Previously this raced the ai-agent /packing endpoint first, but that path
    silently dropped activities/trip_style/bag_size/rag_context and needed
    output-shape glue, so trip packing diverged from the /ai/packing route.
    The agent endpoint still exists for the async ai-worker path.)
    """
    prof = await load_merged_user_profile_for_ai(session, user_id, None)

    async def _run() -> dict[str, Any]:
        return await packing_service.generate_packing_list(
            destination,
            start_date,
            end_date,
            purpose,
            closet_items,
            notes=notes,
            activities=activities,
            trip_style=trip_style,
            bag_size=bag_size,
            user_style_profile=prof,
            rag_context=rag_context,
        )

    try:
        return await asyncio.wait_for(_run(), timeout=50.0)
    except TimeoutError:
        logger.warning("trip_packing_total_timeout", destination=destination)
        return await packing_service.generate_packing_list(
            destination,
            start_date,
            end_date,
            purpose,
            closet_items,
            notes=notes,
            activities=activities,
            trip_style=trip_style,
            bag_size=bag_size,
            user_style_profile=prof,
            rag_context=rag_context,
        )


# ── List / Get ────────────────────────────────────────────────────────────────


@router.get("/", response_model=TripListResponse)
async def list_trips(
    user_id: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await _get_svc(session).list_trips(UUID(user_id))


@router.get("/saved", response_model=TripListResponse)
async def list_saved_trips(
    user_id: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    return await _get_svc(session).list_saved_trips(UUID(user_id))


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    return await _get_svc(session).get_trip(trip_id, UUID(user_id))


@router.get("/{trip_id}/packing-list")
async def get_packing_list(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = _get_svc(session)
    trip_resp = await svc.get_trip(trip_id, UUID(user_id))
    # Fetch raw trip for activities/bag_size
    from sqlalchemy import select as sa_select

    from app.models.trips import Trip as TripModel

    stmt = sa_select(TripModel).where(TripModel.id == trip_id, TripModel.user_id == UUID(user_id))
    raw = await session.execute(stmt)
    trip_orm = raw.scalar_one_or_none()

    closet_items = await _fetch_closet_items(session, UUID(user_id))
    acts = (trip_orm.activities or []) if trip_orm else []
    rag_context = await _build_packing_rag_context(
        session, UUID(user_id), trip_resp.destination, trip_resp.purpose, acts
    )
    return await _generate_trip_packing(
        session,
        UUID(user_id),
        trip_resp.destination,
        str(trip_resp.start_date),
        str(trip_resp.end_date),
        trip_resp.purpose,
        closet_items,
        notes=trip_resp.notes,
        activities=acts,
        trip_style=trip_resp.trip_style,
        bag_size=trip_resp.bag_size,
        rag_context=rag_context,
    )


# ── Create ────────────────────────────────────────────────────────────────────


@router.post("/", response_model=CreateTripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    user_id: CurrentUser,
    body: TripCreate,
    session: AsyncSession = Depends(get_session),
):
    # Same-day is valid: single-event "occasion" plans send start == end.
    if body.end_date < body.start_date:
        raise BadRequestError("end_date must be on or after start_date")
    svc = _get_svc(session)
    trip = await svc.create_trip(UUID(user_id), body)

    closet_items = await _fetch_closet_items(session, UUID(user_id))
    activities = trip.activities or []

    packing_rag_ctx = await _build_packing_rag_context(
        session, UUID(user_id), trip.destination, trip.purpose, activities
    )
    packing_plan = None
    packing_error = None
    packing_result: dict[str, Any] | None = None
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
            activities=activities,
            trip_style=trip.trip_style,
            bag_size=trip.bag_size,
            rag_context=packing_rag_ctx,
        )
        packing_plan = await svc.save_packing_plan(trip.id, UUID(user_id), packing_result)
    except Exception as exc:
        packing_error = str(exc)

    # Persist packing memory and detect purchase gaps (non-blocking)
    if packing_result:
        try:
            packed_ids = [
                str(item.get("item_id") or "")
                for item in packing_result.get("take_from_your_closet", [])
                if item.get("item_id")
            ]
            missing = packing_result.get("you_might_still_need", [])
            await save_packing_memory(
                session,
                user_id=user_id,
                trip_id=str(trip.id),
                destination=trip.destination,
                start_date=trip.start_date.isoformat(),
                end_date=trip.end_date.isoformat(),
                purpose=trip.purpose,
                weather_summary=packing_result.get("weather_summary"),
                packed_item_ids=packed_ids,
                missing_items=missing,
                saved_plan_id=str(packing_plan.id) if packing_plan else None,
            )
            await detect_and_save_gaps(
                session,
                user_id=user_id,
                closet_items=closet_items,
                missing_packing_items=missing,
                trip_context={
                    "destination": trip.destination,
                    "purpose": trip.purpose,
                    "start_date": trip.start_date.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("packing_memory_save_failed", error=str(exc))

    return CreateTripResponse(
        trip=svc._to_response(trip),
        packing_plan=packing_plan,
        packing_error=packing_error,
    )


# ── Activities ────────────────────────────────────────────────────────────────


@router.post("/{trip_id}/activities", response_model=TripResponse)
async def add_trip_activities(
    user_id: CurrentUser,
    trip_id: UUID,
    body: AddActivitiesRequest,
    session: AsyncSession = Depends(get_session),
):
    """Add or replace activities for an existing trip."""
    return await _get_svc(session).add_activities(trip_id, UUID(user_id), body)


# ── Regenerate packing plan ───────────────────────────────────────────────────


@router.post("/{trip_id}/regenerate-packing", response_model=PackingPlanResponse)
async def regenerate_packing_plan(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Regenerate the packing plan for a trip (e.g. after updating activities)."""
    from sqlalchemy import select as sa_select

    from app.models.trips import Trip as TripModel

    stmt = sa_select(TripModel).where(TripModel.id == trip_id, TripModel.user_id == UUID(user_id))
    raw = await session.execute(stmt)
    trip = raw.scalar_one_or_none()
    if not trip:
        raise NotFoundError(f"Trip {trip_id} not found")

    svc = _get_svc(session)
    closet_items = await _fetch_closet_items(session, UUID(user_id))
    acts = trip.activities or []
    rag_context = await _build_packing_rag_context(session, UUID(user_id), trip.destination, trip.purpose, acts)
    packing_result = await _generate_trip_packing(
        session,
        UUID(user_id),
        trip.destination,
        trip.start_date.isoformat(),
        trip.end_date.isoformat(),
        trip.purpose,
        closet_items,
        notes=trip.notes,
        activities=acts,
        trip_style=trip.trip_style,
        bag_size=trip.bag_size,
        rag_context=rag_context,
    )
    return await svc.save_packing_plan(trip.id, UUID(user_id), packing_result)


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


# ── Checklist state ────────────────────────────────────────────────────────────


@router.patch("/{trip_id}/planner/checklist", status_code=status.HTTP_200_OK)
async def update_checklist_item(
    user_id: CurrentUser,
    trip_id: UUID,
    body: ChecklistUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Toggle a single checklist item's packed status (persisted)."""
    return await _get_svc(session).update_checklist_state(trip_id, UUID(user_id), body.item_key, body.is_packed)


# ── Save planner ─────────────────────────────────────────────────────────────


@router.post("/{trip_id}/save-planner", response_model=SavePlannerResponse)
async def save_planner(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    return await _get_svc(session).mark_as_saved(trip_id, UUID(user_id))


# ── Update ────────────────────────────────────────────────────────────────────


@router.patch("/{trip_id}", response_model=TripResponse)
async def update_trip(
    user_id: CurrentUser,
    trip_id: UUID,
    body: TripCreate,
    session: AsyncSession = Depends(get_session),
):
    return await _get_svc(session).update_trip(trip_id, UUID(user_id), body)


# ── Delete ────────────────────────────────────────────────────────────────────


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    user_id: CurrentUser,
    trip_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    await _get_svc(session).delete_trip(trip_id, UUID(user_id))
