from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError
from app.api.v1.wardrobe.schemas.closet import ClosetItemUpdate
from app.core import cache_service
from app.api.v1.wardrobe.services.closet_service import ClosetService


def closet_item(user_id, category="tops", name="Oxford Shirt"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        name=name,
        category=category,
        section=None,
        subcategory=None,
        color="blue",
        fabric=None,
        pattern=None,
        fit=None,
        size=None,
        brand=None,
        image_url=None,
        occasion=["casual"],
        season=["spring"],
        tags=[],
        eco_score=None,
        notes=None,
        price=None,
        wear_count=0,
        last_worn=None,
        is_archived=False,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_get_items_filters_by_category(monkeypatch):
    monkeypatch.setattr(cache_service, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(cache_service, "set", AsyncMock())
    user_id = uuid4()
    service = ClosetService(MagicMock())
    service.repo.get_by_user = AsyncMock(return_value=[closet_item(user_id, "tops")])
    service.repo.count_by_user = AsyncMock(return_value=1)

    response = await service.list_items(user_id, category="tops")

    service.repo.get_by_user.assert_awaited_once()
    assert service.repo.get_by_user.await_args.kwargs["category"] == "tops"
    assert all(i.category == "tops" for i in response.items)


@pytest.mark.asyncio
async def test_get_items_returns_only_own_items(monkeypatch):
    monkeypatch.setattr(cache_service, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(cache_service, "set", AsyncMock())
    user_id = uuid4()
    service = ClosetService(MagicMock())
    service.repo.get_by_user = AsyncMock(return_value=[closet_item(user_id)])
    service.repo.count_by_user = AsyncMock(return_value=1)

    await service.list_items(user_id)

    assert service.repo.get_by_user.await_args.args[0] == user_id


@pytest.mark.asyncio
async def test_update_item_wrong_user_raises_404():
    service = ClosetService(MagicMock())
    service.repo.get_owned = AsyncMock(return_value=None)

    with pytest.raises(NotFoundError) as exc:
        await service.update_item(uuid4(), uuid4(), ClosetItemUpdate(name="New Name"))

    assert exc.value.status_code == 404
