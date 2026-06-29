"""Unit tests — "Complete My Look" (shopping) RAG grounding & anti-hallucination.

Covers the only LLM-generated branch of the Shop with FANI flow,
``get_closet_match_suggestions``. The deterministic buy/skip verdict can't
hallucinate; this branch can, so we assert the grounding guards hold:

  1. The model is called in *grounded* mode — JSON mode on, low temperature,
     and the prompt carries the cite-[SOURCE-N] knowledge contract.
  2. Owned-item references the model invents (numbers outside the real
     inventory, or duplicates) are dropped — only real closet rows survive.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.intelligence.services import shopping_check_service as svc


# ── Fake DB plumbing ──────────────────────────────────────────────────────────


class _Mappings:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)


def _fake_session(item_row: dict, inventory: list[dict]) -> AsyncMock:
    """Session whose two SELECTs return the selected item then the inventory."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_Result([item_row]), _Result(inventory)])
    return session


# ── Fixtures ──────────────────────────────────────────────────────────────────

USER = str(uuid.uuid4())
ITEM_ID = str(uuid.uuid4())
PANTS_ID = str(uuid.uuid4())
SHOES_ID = str(uuid.uuid4())


def _item_row() -> dict:
    return {
        "id": ITEM_ID,
        "name": "Navy Blazer",
        "category": "outerwear",
        "color": "navy",
        "fabric": "wool",
        "pattern": "solid",
        "brand": "",
        "season": ["fall"],
        "occasion": ["business casual"],
        "tags": [],
        "notes": "",
        "image_url": "http://img/blazer.jpg",
        "processed_image_url": None,
    }


def _inventory() -> list[dict]:
    return [
        {"id": PANTS_ID, "name": "Grey Chinos", "category": "bottoms",
         "color": "grey", "occasion": ["business casual"],
         "image_url": "http://img/chinos.jpg", "processed_image_url": None},
        {"id": SHOES_ID, "name": "Brown Loafers", "category": "shoes",
         "color": "brown", "occasion": ["business casual"],
         "image_url": "http://img/loafers.jpg", "processed_image_url": None},
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_match_suggestions_calls_model_in_grounded_mode():
    """AI is invoked with JSON mode, low temperature, and the cite contract."""
    session = _fake_session(_item_row(), _inventory())
    chat_mock = AsyncMock(return_value=json.dumps({
        "outfit_potential": "high",
        "styling_tip": "Pair with neutrals [SOURCE-1].",
        "closet_pairings": [{"item_number": 1, "role": "bottom", "reason": "neutral pairing [SOURCE-1]"}],
        "suggestions": [],
    }))

    with patch.object(svc.ai_service, "chat", chat_mock), patch.object(
        svc, "get_fashion_context_for_prompt",
        new=AsyncMock(return_value="[SOURCE-1] Color Matching Fundamentals\nNeutrals pair with anything."),
    ):
        out = await svc.get_closet_match_suggestions(ITEM_ID, USER, session)

    assert chat_mock.await_count == 1
    kwargs = chat_mock.await_args.kwargs
    assert kwargs["use_json_mode"] is True
    assert kwargs["temperature"] <= 0.3
    user_msg = chat_mock.await_args.kwargs["messages"][0]["content"]
    assert "[SOURCE-1]" in user_msg
    assert "cite [SOURCE-N]" in user_msg
    assert out["grounded_in_knowledge"] is True


@pytest.mark.asyncio
async def test_hallucinated_owned_item_numbers_are_dropped():
    """Out-of-range and duplicate item_number references never reach the response."""
    session = _fake_session(_item_row(), _inventory())
    # Model references: a valid #1, a hallucinated #99, and a duplicate #1.
    chat_mock = AsyncMock(return_value=json.dumps({
        "outfit_potential": "medium",
        "styling_tip": "Looks sharp.",
        "closet_pairings": [
            {"item_number": 1, "role": "bottom", "reason": "works"},
            {"item_number": 99, "role": "shoes", "reason": "invented item"},
            {"item_number": 1, "role": "bottom", "reason": "duplicate"},
        ],
        "suggestions": [],
    }))

    with patch.object(svc.ai_service, "chat", chat_mock), patch.object(
        svc, "get_fashion_context_for_prompt", new=AsyncMock(return_value=""),
    ):
        out = await svc.get_closet_match_suggestions(ITEM_ID, USER, session)

    pairings = out["closet_pairings"]
    pairing_ids = {p["id"] for p in pairings}
    assert PANTS_ID in pairing_ids  # valid AI reference kept
    assert len(pairing_ids) == len(pairings)  # AI duplicate #1 de-duped
    assert all(pid in {PANTS_ID, SHOES_ID} for pid in pairing_ids)  # #99 never appears
    assert out["grounded_in_knowledge"] is False  # empty RAG context


@pytest.mark.asyncio
async def test_unparseable_model_output_falls_back_safely():
    """A non-JSON model reply degrades to a safe default, never raises."""
    session = _fake_session(_item_row(), _inventory())
    with patch.object(svc.ai_service, "chat", new=AsyncMock(return_value="sorry, I can't")), patch.object(
        svc, "get_fashion_context_for_prompt", new=AsyncMock(return_value=""),
    ):
        out = await svc.get_closet_match_suggestions(ITEM_ID, USER, session)

    # Deterministic best-combination pairings still surface when the model fails.
    assert len(out["closet_pairings"]) >= 1
    assert out["suggestions"] == []
    assert out["outfit_potential"] in {"low", "medium", "high"}
