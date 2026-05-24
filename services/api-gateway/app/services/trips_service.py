"""TripsService — handles trip CRUD and packing plan persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.packing import PackingPlan
from app.models.trips import Trip
from app.schemas.trips import (
    AddActivitiesRequest,
    PackingPlanResponse,
    SavePlannerResponse,
    TripCreate,
    TripListResponse,
    TripResponse,
)


class TripsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_trips(self, user_id: UUID) -> TripListResponse:
        stmt = select(Trip).where(Trip.user_id == user_id).order_by(Trip.start_date.desc())
        result = await self.session.execute(stmt)
        trips = result.scalars().all()
        return TripListResponse(
            trips=[self._to_response(t) for t in trips],
            total=len(trips),
        )

    async def list_saved_trips(self, user_id: UUID) -> TripListResponse:
        stmt = (
            select(Trip)
            .where(Trip.user_id == user_id, Trip.is_saved == True)  # noqa: E712
            .order_by(Trip.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        trips = result.scalars().all()
        return TripListResponse(
            trips=[self._to_response(t) for t in trips],
            total=len(trips),
        )

    async def mark_as_saved(self, trip_id: UUID, user_id: UUID) -> SavePlannerResponse:
        trip_stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        trip_result = await self.session.execute(trip_stmt)
        trip = trip_result.scalar_one_or_none()
        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")

        plan_stmt = select(PackingPlan).where(PackingPlan.trip_id == trip_id, PackingPlan.user_id == user_id)
        plan_result = await self.session.execute(plan_stmt)
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise NotFoundError(f"No packing plan found for trip {trip_id}. Generate a packing plan first.")

        already_saved = trip.is_saved and plan.is_saved
        trip.is_saved = True
        plan.is_saved = True
        plan.updated_at = datetime.now(timezone.utc)
        trip.updated_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(trip)
        await self.session.refresh(plan)

        message = "Planner is already saved." if already_saved else "Planner saved successfully."
        return SavePlannerResponse(
            message=message,
            trip=self._to_response(trip),
            packing_plan=self._plan_to_response(plan, plan.raw_result or {}),
        )

    async def get_trip(self, trip_id: UUID, user_id: UUID) -> TripResponse:
        stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        result = await self.session.execute(stmt)
        trip = result.scalar_one_or_none()
        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")
        return self._to_response(trip)

    async def create_trip(self, user_id: UUID, data: TripCreate) -> Trip:
        """Create a Trip ORM object (returns the raw model, not response schema)."""
        if data.end_date <= data.start_date:
            raise BadRequestError("end_date must be after start_date")
        trip = Trip(
            user_id=user_id,
            destination=data.destination,
            start_date=data.start_date,
            end_date=data.end_date,
            purpose=data.purpose,
            trip_style=data.trip_style,
            bag_size=data.bag_size,
            notes=data.notes,
            activities=[a.model_dump() for a in (data.activities or [])],
        )
        self.session.add(trip)
        await self.session.flush()
        await self.session.refresh(trip)
        return trip

    async def update_trip(self, trip_id: UUID, user_id: UUID, data: TripCreate) -> TripResponse:
        if data.end_date <= data.start_date:
            raise BadRequestError("end_date must be after start_date")
        stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        result = await self.session.execute(stmt)
        trip = result.scalar_one_or_none()
        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")

        trip.destination = data.destination
        trip.start_date = data.start_date
        trip.end_date = data.end_date
        trip.purpose = data.purpose
        trip.trip_style = data.trip_style
        trip.bag_size = data.bag_size
        trip.notes = data.notes
        if data.activities is not None:
            trip.activities = [a.model_dump() for a in data.activities]

        await self.session.flush()
        await self.session.refresh(trip)
        return self._to_response(trip)

    async def add_activities(
        self, trip_id: UUID, user_id: UUID, body: AddActivitiesRequest
    ) -> TripResponse:
        stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        result = await self.session.execute(stmt)
        trip = result.scalar_one_or_none()
        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")

        new_acts = [a.model_dump() for a in body.activities]
        if body.replace:
            trip.activities = new_acts
        else:
            existing = list(trip.activities or [])
            existing.extend(new_acts)
            trip.activities = existing

        trip.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(trip)
        return self._to_response(trip)

    async def update_checklist_state(
        self,
        trip_id: UUID,
        user_id: UUID,
        item_key: str,
        is_packed: bool,
    ) -> dict[str, Any]:
        """Toggle a single checklist item's packed status."""
        plan_stmt = select(PackingPlan).where(PackingPlan.trip_id == trip_id, PackingPlan.user_id == user_id)
        plan_result = await self.session.execute(plan_stmt)
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise NotFoundError(f"No packing plan found for trip {trip_id}")

        state = dict(plan.checklist_state or {})
        state[item_key] = is_packed
        plan.checklist_state = state
        plan.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return {"item_key": item_key, "is_packed": is_packed}

    async def delete_trip(self, trip_id: UUID, user_id: UUID) -> None:
        stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        result = await self.session.execute(stmt)
        trip = result.scalar_one_or_none()
        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")
        await self.session.delete(trip)
        await self.session.flush()

    async def save_packing_plan(
        self,
        trip_id: UUID,
        user_id: UUID,
        packing_result: dict[str, Any],
    ) -> PackingPlanResponse:
        stmt = select(PackingPlan).where(PackingPlan.trip_id == trip_id, PackingPlan.user_id == user_id)
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()

        take = packing_result.get("take_from_your_closet") or []
        need = packing_result.get("you_might_still_need") or []
        daily = packing_result.get("daily_plan") or []
        weather = packing_result.get("weather_summary")
        day_plans_rich = packing_result.get("day_plans_rich") or []
        rewear = packing_result.get("rewear_strategy") or []
        bag_cap = packing_result.get("bag_capacity_summary") or {}
        checklist = packing_result.get("packing_checklist") or []
        activities = packing_result.get("activities") or []

        if plan:
            plan.take_from_your_closet = take
            plan.you_might_still_need = need
            plan.daily_plan = daily
            plan.weather_summary = weather
            plan.raw_result = packing_result
            plan.day_plans_rich = day_plans_rich
            plan.rewear_strategy = rewear
            plan.bag_capacity_summary = bag_cap
            plan.packing_checklist = checklist
            plan.activities = activities
            plan.updated_at = datetime.now(timezone.utc)
        else:
            plan = PackingPlan(
                id=uuid.uuid4(),
                trip_id=trip_id,
                user_id=user_id,
                take_from_your_closet=take,
                you_might_still_need=need,
                daily_plan=daily,
                weather_summary=weather,
                raw_result=packing_result,
                day_plans_rich=day_plans_rich,
                rewear_strategy=rewear,
                bag_capacity_summary=bag_cap,
                packing_checklist=checklist,
                activities=activities,
            )
            self.session.add(plan)

        await self.session.flush()
        await self.session.refresh(plan)
        return self._plan_to_response(plan, packing_result)

    async def get_packing_plan(self, trip_id: UUID, user_id: UUID) -> PackingPlanResponse | None:
        stmt = select(PackingPlan).where(PackingPlan.trip_id == trip_id, PackingPlan.user_id == user_id)
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()
        if not plan:
            return None
        return self._plan_to_response(plan, plan.raw_result or {})

    def _plan_to_response(self, plan: PackingPlan, raw: dict[str, Any]) -> PackingPlanResponse:
        # Merge checklist with persisted packed state
        checklist = list(plan.packing_checklist or raw.get("packing_checklist") or [])
        state = plan.checklist_state or {}
        for item in checklist:
            key = str(item.get("closet_item_id") or item.get("item_name", "")).lower()
            if key in state:
                item["is_packed"] = state[key]

        return PackingPlanResponse(
            id=plan.id,
            trip_id=plan.trip_id,
            user_id=plan.user_id,
            take_from_your_closet=plan.take_from_your_closet or [],
            you_might_still_need=plan.you_might_still_need or [],
            daily_plan=plan.daily_plan or [],
            weather_summary=plan.weather_summary,
            packing_list=raw.get("packing_list") or [],
            missing_items=raw.get("missing_items") or [],
            summary=raw.get("summary"),
            closet_hint=raw.get("closet_hint"),
            alerts=raw.get("alerts") or [],
            # New fields
            activities=plan.activities or raw.get("activities") or [],
            day_plans_rich=plan.day_plans_rich or raw.get("day_plans_rich") or [],
            rewear_strategy=plan.rewear_strategy or raw.get("rewear_strategy") or [],
            bag_capacity_summary=plan.bag_capacity_summary or raw.get("bag_capacity_summary") or {},
            packing_checklist=checklist,
            checklist_state=state,
            trip_style_direction=raw.get("trip_style_direction"),
            climate_summary=raw.get("climate_summary"),
            is_saved=plan.is_saved,
            created_at=plan.created_at.isoformat(),
            updated_at=plan.updated_at.isoformat(),
        )

    def _to_response(self, trip: Trip) -> TripResponse:
        return TripResponse(
            id=trip.id,
            user_id=trip.user_id,
            destination=trip.destination,
            start_date=trip.start_date,
            end_date=trip.end_date,
            purpose=trip.purpose,
            notes=trip.notes,
            trip_style=trip.trip_style,
            bag_size=trip.bag_size,
            activities=trip.activities or [],
            is_saved=trip.is_saved,
            created_at=trip.created_at.isoformat(),
            updated_at=trip.updated_at.isoformat(),
        )
