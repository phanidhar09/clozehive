"""Condition field: prompt-serialization passthrough + create-time default guard.

Locks in the Step-2 wiring:
- condition surfaces in the item dicts the AI prompt is built from
  (outfit_ai_service._item_for_ai and ai._item_dict), so FANI can weigh it.
- create_item never sends condition=None (would violate the NOT NULL column);
  an omitted condition falls through to the DB server_default.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.intelligence.ai import _item_dict
from app.api.v1.wardrobe.schemas.closet import ClosetItemCreate
from app.api.v1.wardrobe.services.closet_service import ClosetService
from app.api.v1.wardrobe.services.outfit_ai_service import _item_for_ai
from app.constants.wardrobe import CONDITION_RANK, Condition
from app.core import cache_service


def test_condition_rank_is_ordinal_and_damaged_is_floor():
    assert CONDITION_RANK[Condition.NEW] > CONDITION_RANK[Condition.WORN]
    assert CONDITION_RANK[Condition.DAMAGED] == min(CONDITION_RANK.values())


def test_item_for_ai_surfaces_condition():
    out = _item_for_ai({"id": uuid4(), "name": "Blazer", "condition": "worn"})
    assert out["condition"] == "worn"


def test_item_for_ai_condition_defaults_to_blank_when_absent():
    # Missing condition must not crash the prompt build; renders as "".
    assert _item_for_ai({"id": uuid4(), "name": "Tee"})["condition"] == ""


def test_ai_item_dict_surfaces_condition():
    item = SimpleNamespace(
        id=uuid4(),
        name="Oxford Shirt",
        category="tops",
        color="blue",
        fit=None,
        occasion=["casual"],
        season=["spring"],
        wear_count=3,
        condition="excellent",
    )
    assert _item_dict(item)["condition"] == "excellent"


@pytest.mark.asyncio
async def test_create_item_omits_none_condition(monkeypatch):
    # An unspecified condition must be dropped so the DB server_default applies —
    # passing condition=None would violate the NOT NULL column.
    monkeypatch.setattr(cache_service, "invalidate_closet_list_cache", AsyncMock())
    service = ClosetService(MagicMock())
    service.repo.create = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            name="Tee",
            category="tops",
            color=None,
            fabric=None,
            pattern=None,
            season=[],
            occasion=None,
            eco_score=None,
            tags=None,
            image_url=None,
            notes=None,
            brand=None,
            size=None,
            fit=None,
            measurements=None,
            price=None,
            wear_count=0,
            last_worn=None,
            is_archived=False,
            availability="available",
            condition="good",
            created_at=__import__("datetime").datetime.now(),
            updated_at=__import__("datetime").datetime.now(),
            original_image_url=None,
            processed_image_url=None,
            background_removed=False,
            background_removal_status=None,
            analysis_source=None,
            confidence_score=None,
            scan_batch_id=None,
        )
    )

    await service.create_item(uuid4(), ClosetItemCreate(name="Tee", category="tops"))

    assert "condition" not in service.repo.create.await_args.kwargs


@pytest.mark.asyncio
async def test_create_item_passes_explicit_condition(monkeypatch):
    monkeypatch.setattr(cache_service, "invalidate_closet_list_cache", AsyncMock())
    service = ClosetService(MagicMock())
    captured = {}

    async def _fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id=uuid4(),
            user_id=kwargs["user_id"],
            name=kwargs["name"],
            category=kwargs["category"],
            color=None,
            fabric=None,
            pattern=None,
            season=[],
            occasion=None,
            eco_score=None,
            tags=None,
            image_url=None,
            notes=None,
            brand=None,
            size=None,
            fit=None,
            measurements=None,
            price=None,
            wear_count=0,
            last_worn=None,
            is_archived=False,
            availability="available",
            condition=kwargs.get("condition", "good"),
            created_at=__import__("datetime").datetime.now(),
            updated_at=__import__("datetime").datetime.now(),
            original_image_url=None,
            processed_image_url=None,
            background_removed=False,
            background_removal_status=None,
            analysis_source=None,
            confidence_score=None,
            scan_batch_id=None,
        )

    service.repo.create = _fake_create

    await service.create_item(
        uuid4(), ClosetItemCreate(name="Suit", category="tops", condition="new")
    )

    assert captured["condition"] == "new"
