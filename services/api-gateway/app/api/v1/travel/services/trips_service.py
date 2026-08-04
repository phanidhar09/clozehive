"""TripsService — handles trip CRUD and packing plan persistence."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.v1.travel.schemas.trips import (
    AddActivitiesRequest,
    PackingPlanResponse,
    SavePlannerResponse,
    TripCreate,
    TripListResponse,
    TripResponse,
)
from app.api.v1.travel.services import packing_service
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.packing import PackingPlan
from app.models.trips import Trip


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
        plan.updated_at = datetime.now(UTC)
        trip.updated_at = datetime.now(UTC)

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
        # Same-day is valid: single-event "occasion" plans send start == end.
        if data.end_date < data.start_date:
            raise BadRequestError("end_date must be on or after start_date")
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
        # Same-day is valid: single-event "occasion" plans send start == end.
        if data.end_date < data.start_date:
            raise BadRequestError("end_date must be on or after start_date")
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

    async def add_activities(self, trip_id: UUID, user_id: UUID, body: AddActivitiesRequest) -> TripResponse:
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

        trip.updated_at = datetime.now(UTC)
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
        plan.updated_at = datetime.now(UTC)
        await self.session.flush()
        return {"item_key": item_key, "is_packed": is_packed}

    # ── Plan editing ──────────────────────────────────────────────────────────
    # Every derived section (checklist, bag capacity, closet-take list, legacy
    # daily plan, rewear) is recomputed from day_plans_rich with no LLM call, so
    # edits are instant and free. User intent is additionally recorded in
    # ``user_edits`` so a later "Regenerate Plan" can preserve it.

    async def get_plan_row(self, trip_id: UUID, user_id: UUID) -> PackingPlan | None:
        """Return the raw PackingPlan ORM row (or None) — for callers needing user_edits."""
        stmt = select(PackingPlan).where(PackingPlan.trip_id == trip_id, PackingPlan.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_plan_or_404(self, trip_id: UUID, user_id: UUID) -> PackingPlan:
        stmt = select(PackingPlan).where(PackingPlan.trip_id == trip_id, PackingPlan.user_id == user_id)
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()
        if not plan:
            raise NotFoundError(f"No packing plan found for trip {trip_id}")
        return plan

    async def _rederive_and_persist(
        self,
        plan: PackingPlan,
        closet_items: list[dict[str, Any]],
        trip_days: int,
        bag_size: str | None,
    ) -> PackingPlanResponse:
        """Re-run the derive chain over the current day plans and save."""
        raw = dict(plan.raw_result or {})
        derived = packing_service.recompute_plan_sections(
            deepcopy(list(plan.day_plans_rich or [])),
            closet_items=closet_items,
            missing_items=raw.get("missing_items_rich") or [],
            rewear_strategy=list(plan.rewear_strategy or []),
            trip_days=trip_days,
            bag_size=bag_size,
            user_edits=dict(plan.user_edits or {}),
        )
        plan.day_plans_rich = derived["day_plans_rich"]
        plan.rewear_strategy = derived["rewear_strategy"]
        plan.bag_capacity_summary = derived["bag_capacity_summary"]
        plan.packing_checklist = derived["packing_checklist"]
        plan.daily_plan = derived["daily_plan"]
        plan.take_from_your_closet = derived["take_from_your_closet"]
        plan.you_might_still_need = derived["you_might_still_need"]
        plan.checklist_state = self._reconcile_checklist_state(
            dict(plan.checklist_state or {}), derived["packing_checklist"]
        )
        # Keep raw_result in step so a later regenerate reads the edited plan.
        raw.update(
            {
                "day_plans_rich": derived["day_plans_rich"],
                "rewear_strategy": derived["rewear_strategy"],
                "bag_capacity_summary": derived["bag_capacity_summary"],
                "packing_checklist": derived["packing_checklist"],
            }
        )
        plan.raw_result = raw
        plan.updated_at = datetime.now(UTC)
        # JSONB columns are NOT change-tracked on in-place mutation, and an edit
        # can hand back a structure SQLAlchemy considers identical to the loaded
        # one — in which case no UPDATE is emitted and the edit is silently lost
        # on refresh. Flag every JSONB column we just wrote so the write always
        # reaches the database.
        for column in (
            "day_plans_rich",
            "rewear_strategy",
            "bag_capacity_summary",
            "packing_checklist",
            "daily_plan",
            "take_from_your_closet",
            "you_might_still_need",
            "checklist_state",
            "user_edits",
            "raw_result",
        ):
            flag_modified(plan, column)
        await self.session.flush()
        await self.session.refresh(plan)
        return self._plan_to_response(plan, raw)

    @staticmethod
    def _reconcile_checklist_state(state: dict[str, Any], checklist: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Drop packed-state keys that no longer match any checklist row.

        Without this, editing or regenerating a plan leaves orphaned booleans
        behind that silently re-apply if an item with the same key reappears.
        """
        live = {packing_service.checklist_key(item) for item in checklist}
        return {k: v for k, v in state.items() if k in live}

    @staticmethod
    def _pin_day(user_edits: dict[str, Any], day_number: int) -> None:
        pinned = {int(d) for d in (user_edits.get("pinned_days") or []) if str(d).isdigit()}
        pinned.add(int(day_number))
        user_edits["pinned_days"] = sorted(pinned)

    async def edit_outfit_items(
        self,
        trip_id: UUID,
        user_id: UUID,
        *,
        day_number: int,
        slot: str,
        operation: str,
        closet_item_id: str | None,
        replace_item_id: str | None,
        closet_items: list[dict[str, Any]],
        trip_days: int,
        bag_size: str | None,
    ) -> PackingPlanResponse:
        """
        Add / remove / swap a single item inside one outfit, then re-derive.

        The edited day is pinned so a later regenerate leaves it untouched, and
        the outfit's styling prose is flagged stale (it may now describe an item
        that is no longer in the outfit).
        """
        plan = await self._get_plan_or_404(trip_id, user_id)
        # Deep copy: the outfit dicts are mutated below, and mutating the loaded
        # ORM value in place would both escape SQLAlchemy's change detection and
        # leave a half-applied edit behind if validation rejects the request.
        day_plans = deepcopy(list(plan.day_plans_rich or []))

        day = next((d for d in day_plans if int(d.get("day_number") or 0) == int(day_number)), None)
        if day is None:
            raise NotFoundError(f"Day {day_number} not found in this plan")
        outfit = next((o for o in day.get("outfits", []) if str(o.get("slot")) == slot), None)
        if outfit is None:
            raise NotFoundError(f"No '{slot}' outfit on day {day_number}")

        closet_by_id = {str(c["id"]): c for c in closet_items if c.get("id")}
        items: list[dict[str, Any]] = list(outfit.get("items") or [])

        def _new_item(cid: str) -> dict[str, Any]:
            # Ownership is enforced by the caller; this only shapes the entry.
            real = closet_by_id[cid]
            return {
                "closet_item_id": cid,
                "item_name": real.get("name") or "Wardrobe item",
                "category": real.get("category") or "general",
                "source": "from_closet",
                "image_url": real.get("image_url") or None,
            }

        if operation in ("add", "swap") and (not closet_item_id or closet_item_id not in closet_by_id):
            raise BadRequestError("closet_item_id must reference an item in your closet")

        if operation == "add":
            if any(str(i.get("closet_item_id") or "") == closet_item_id for i in items):
                raise BadRequestError("That item is already in this outfit")
            items.append(_new_item(str(closet_item_id)))
        elif operation == "remove":
            target = replace_item_id or closet_item_id
            before = len(items)
            items = [i for i in items if str(i.get("closet_item_id") or "") != str(target)]
            if len(items) == before:
                raise NotFoundError("That item is not in this outfit")
        elif operation == "swap":
            if not replace_item_id:
                raise BadRequestError("swap requires replace_item_id (the item being replaced)")
            idx = next(
                (n for n, i in enumerate(items) if str(i.get("closet_item_id") or "") == str(replace_item_id)),
                None,
            )
            if idx is None:
                raise NotFoundError("The item being replaced is not in this outfit")
            items[idx] = _new_item(str(closet_item_id))
        else:
            raise BadRequestError(f"Unknown operation '{operation}' (expected add, remove or swap)")

        outfit["items"] = items
        # The prose was written for the previous item set — flag, don't silently keep.
        outfit["notes_stale"] = True

        user_edits = dict(plan.user_edits or {})
        self._pin_day(user_edits, day_number)
        log = list(user_edits.get("outfit_edits") or [])
        log.append(
            {
                "day_number": int(day_number),
                "slot": slot,
                "operation": operation,
                "closet_item_id": closet_item_id,
                "replace_item_id": replace_item_id,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        user_edits["outfit_edits"] = log[-100:]  # bounded audit trail
        plan.user_edits = user_edits
        plan.day_plans_rich = day_plans

        return await self._rederive_and_persist(plan, closet_items, trip_days, bag_size)

    async def add_checklist_items(
        self,
        trip_id: UUID,
        user_id: UUID,
        *,
        closet_item_ids: list[str],
        note: str | None,
        closet_items: list[dict[str, Any]],
        trip_days: int,
        bag_size: str | None,
    ) -> PackingPlanResponse:
        """Pack extra closet items that aren't in any planned outfit."""
        plan = await self._get_plan_or_404(trip_id, user_id)
        owned = {str(c["id"]) for c in closet_items if c.get("id")}
        unknown = [i for i in closet_item_ids if i not in owned]
        if unknown:
            raise BadRequestError(f"{len(unknown)} item(s) are not in your closet")

        user_edits = dict(plan.user_edits or {})
        added = list(user_edits.get("checklist_added") or [])
        existing = {str(a.get("closet_item_id")) for a in added if isinstance(a, dict)}
        for cid in closet_item_ids:
            if cid in existing:
                continue
            added.append({"closet_item_id": cid, "note": note, "at": datetime.now(UTC).isoformat()})
            existing.add(cid)
        user_edits["checklist_added"] = added
        # Re-adding an item clears any earlier removal of it.
        removed = [
            k
            for k in (user_edits.get("checklist_removed") or [])
            if str(k).lower() not in {c.lower() for c in closet_item_ids}
        ]
        user_edits["checklist_removed"] = removed
        plan.user_edits = user_edits

        return await self._rederive_and_persist(plan, closet_items, trip_days, bag_size)

    async def remove_checklist_item(
        self,
        trip_id: UUID,
        user_id: UUID,
        *,
        item_key: str,
        closet_items: list[dict[str, Any]],
        trip_days: int,
        bag_size: str | None,
    ) -> PackingPlanResponse:
        """Drop a row from the checklist (works for planned, essential or added rows)."""
        plan = await self._get_plan_or_404(trip_id, user_id)
        user_edits = dict(plan.user_edits or {})

        key = item_key.lower()
        removed = {str(k).lower() for k in (user_edits.get("checklist_removed") or [])}
        removed.add(key)
        user_edits["checklist_removed"] = sorted(removed)
        # A removed row should no longer be re-added by the override replay.
        user_edits["checklist_added"] = [
            a
            for a in (user_edits.get("checklist_added") or [])
            if isinstance(a, dict) and str(a.get("closet_item_id") or "").lower() != key
        ]
        plan.user_edits = user_edits

        return await self._rederive_and_persist(plan, closet_items, trip_days, bag_size)

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
            # user_edits is deliberately NOT overwritten — it is the durable
            # delta layer and must survive every regeneration. Packed-state keys
            # are reconciled instead, so a rebuilt checklist never inherits
            # orphaned booleans from items the new plan dropped.
            plan.checklist_state = self._reconcile_checklist_state(dict(plan.checklist_state or {}), checklist)
            plan.updated_at = datetime.now(UTC)
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
            key = packing_service.checklist_key(item)
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
            pinned_days=[
                int(d) for d in ((getattr(plan, "user_edits", None) or {}).get("pinned_days") or []) if str(d).isdigit()
            ],
            trip_style_direction=raw.get("trip_style_direction"),
            climate_summary=raw.get("climate_summary"),
            location_etiquette=raw.get("location_etiquette"),
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
