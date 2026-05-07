"""
Trip routes — /api/v1/trips/*
MVP: Create, list, get, update trips for travel packing
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.exceptions import BadRequestError, NotFoundError
from app.db.session import get_session
from app.models.closet import ClosetItem
from app.schemas.trips import CreateTripResponse, PackingPlanResponse, SavePlannerResponse, TripCreate, TripResponse, TripListResponse
from app.services import packing_service
from app.services.trips_service import TripsService


router = APIRouter(prefix="/trips", tags=["Trips"])


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
    return await packing_service.generate_packing_list(
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
        packing_result = await packing_service.generate_packing_list(
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
