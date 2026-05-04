from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import NotFoundError
from app.schemas.trips import TripCreate
from app.services.trips_service import TripsService


def trip(user_id):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        destination="Paris",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
        purpose="leisure",
        notes=None,
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
