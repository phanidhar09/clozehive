from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import NotFoundError
from app.api.v1.travel.schemas.trips import TripCreate
from app.api.v1.travel.services.trips_service import TripsService


def trip(user_id, is_saved=False):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        destination="Paris",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
        purpose="leisure",
        notes=None,
        trip_style=None,
        bag_size=None,
        activities=[],
        is_saved=is_saved,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def packing_plan(trip_id, user_id, is_saved=False):
    return SimpleNamespace(
        id=uuid4(),
        trip_id=trip_id,
        user_id=user_id,
        take_from_your_closet=[],
        you_might_still_need=[],
        daily_plan=[],
        weather_summary=None,
        packing_checklist=[],
        checklist_state={},
        activities=[],
        day_plans_rich=[],
        rewear_strategy=[],
        bag_capacity_summary={},
        raw_result={},
        is_saved=is_saved,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def execute_result(trips=None, scalar=None):
    result = MagicMock()
    result.scalars.return_value.all.return_value = trips or []
    result.scalar_one_or_none.return_value = scalar
    return result


@pytest.mark.asyncio
async def test_list_trips_only_returns_own_trips():
    user_a = uuid4()
    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result(trips=[trip(user_a)]))

    result = await TripsService(session).list_trips(user_a)

    assert result.total == 1
    assert all(t.user_id == user_a for t in result.trips)


@pytest.mark.asyncio
async def test_get_trip_wrong_user_raises_404():
    user_a = uuid4()
    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result(scalar=None))

    with pytest.raises(NotFoundError) as exc:
        await TripsService(session).get_trip(uuid4(), user_a)

    assert exc.value.status_code == 404


def test_create_trip_end_before_start_raises_validation():
    with pytest.raises(ValidationError):
        TripCreate(
            destination="Paris",
            start_date=date(2026, 6, 5),
            end_date=date(2026, 6, 1),
            purpose="leisure",
        )


@pytest.mark.asyncio
async def test_delete_trip_wrong_user_raises_404():
    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result(scalar=None))

    with pytest.raises(NotFoundError) as exc:
        await TripsService(session).delete_trip(uuid4(), uuid4())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mark_as_saved_raises_404_when_trip_not_found():
    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result(scalar=None))

    with pytest.raises(NotFoundError):
        await TripsService(session).mark_as_saved(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_mark_as_saved_raises_404_when_no_packing_plan():
    user_id = uuid4()
    t = trip(user_id)
    call_count = 0

    async def side_effect(*_args, **_kw):
        nonlocal call_count
        call_count += 1
        # First call → trip found; second call → no packing plan
        return execute_result(scalar=t if call_count == 1 else None)

    session = MagicMock()
    session.execute = AsyncMock(side_effect=side_effect)

    with pytest.raises(NotFoundError) as exc:
        await TripsService(session).mark_as_saved(t.id, user_id)

    assert "packing plan" in str(exc.value).lower() or exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mark_as_saved_sets_is_saved():
    user_id = uuid4()
    t = trip(user_id)
    plan = packing_plan(t.id, user_id)
    call_count = 0

    async def side_effect(*_args, **_kw):
        nonlocal call_count
        call_count += 1
        return execute_result(scalar=t if call_count == 1 else plan)

    session = MagicMock()
    session.execute = AsyncMock(side_effect=side_effect)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    result = await TripsService(session).mark_as_saved(t.id, user_id)

    assert t.is_saved is True
    assert plan.is_saved is True
    assert result.trip.is_saved is True
    assert result.packing_plan.is_saved is True
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_list_saved_trips_only_returns_saved():
    user_id = uuid4()
    saved = trip(user_id, is_saved=True)
    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result(trips=[saved]))

    result = await TripsService(session).list_saved_trips(user_id)

    assert result.total == 1
    assert result.trips[0].is_saved is True
