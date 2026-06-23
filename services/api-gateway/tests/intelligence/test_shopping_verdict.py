"""Unit tests — Shop with FANI buy/skip verdict.

Two concerns, both core to the product:

  1. ``compute_buy_score`` — the pure scoring engine. The buy score is the most
     important number in the feature; here it's tested in isolation (no vision,
     embeddings, or DB), covering each factor, the recommendation bands, and the
     invariant that the breakdown sums to the score.
  2. ``_generate_grounded_take`` — the RAG-grounded natural-language verdict. The
     deterministic score is authoritative; the model may only *explain* it from
     cited knowledge. We assert it can't hallucinate: no knowledge → no take,
     out-of-range citations are dropped, and bad output degrades to None.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.intelligence.services import shopping_check_service as svc


# ── 1. Pure scoring engine ──────────────────────────────────────────────────────


def test_weights_sum_to_100():
    assert round(sum(svc._WEIGHTS.values())) == 100


def test_breakdown_always_sums_to_score():
    """Whatever the inputs, the per-factor contributions sum to the buy score."""
    import itertools

    for has_dupe, fills_gap, occ, sea in itertools.product([True, False], repeat=4):
        for count in (0, 1, 4, 10):
            score, breakdown, _ = svc.compute_buy_score(
                has_duplicate=has_dupe,
                compatible_count=count,
                fills_gap=fills_gap,
                has_new_occasions=occ,
                has_new_seasons=sea,
            )
            assert score == round(sum(breakdown.values()))
            assert 0 <= score <= 100


def test_strong_unique_compatible_item_is_a_buy():
    score, breakdown, rec = svc.compute_buy_score(
        has_duplicate=False,
        compatible_count=4,  # saturates compatibility
        fills_gap=True,
        has_new_occasions=True,
        has_new_seasons=True,
    )
    assert score == 100
    assert rec == "buy"
    assert breakdown["compatibility"] == 35.0
    assert breakdown["uniqueness"] == 30.0


def test_duplicate_suppresses_uniqueness_and_novelty():
    """A duplicate zeroes uniqueness AND the novelty factors (no double credit)."""
    score, breakdown, rec = svc.compute_buy_score(
        has_duplicate=True,
        compatible_count=4,
        fills_gap=False,
        has_new_occasions=True,  # must NOT count while it's a duplicate
        has_new_seasons=True,
    )
    assert breakdown["uniqueness"] == 0.0
    assert breakdown["occasion_new"] == 0.0
    assert breakdown["season_new"] == 0.0
    assert breakdown["compatibility"] == 35.0
    assert score == 35
    assert rec == "skip"


def test_recommendation_bands():
    # skip: lone gap-fill = 15
    assert svc.compute_buy_score(
        has_duplicate=True, compatible_count=0, fills_gap=True,
        has_new_occasions=False, has_new_seasons=False,
    )[2] == "skip"
    # consider: uniqueness(30) + ~half compatibility(2/4*35=17.5) = 47.5 → 48
    assert svc.compute_buy_score(
        has_duplicate=False, compatible_count=2, fills_gap=False,
        has_new_occasions=False, has_new_seasons=False,
    )[2] == "consider"
    # buy: uniqueness(30) + full compatibility(35) + gap(15) = 80
    assert svc.compute_buy_score(
        has_duplicate=False, compatible_count=4, fills_gap=True,
        has_new_occasions=False, has_new_seasons=False,
    )[2] == "buy"


# ── 2. RAG-grounded take ────────────────────────────────────────────────────────

USER = str(uuid.uuid4())


def _analysis() -> dict:
    return {
        "name": "Navy Wool Blazer",
        "category": "outerwear",
        "primary_color": "navy",
        "occasion_tags": ["business casual"],
    }


async def _call_take(chat_return: str, docs: list[dict]):
    session = AsyncMock()
    with patch.object(svc, "search_fashion_knowledge", new=AsyncMock(return_value=docs)), patch.object(
        svc.ai_service, "chat", new=AsyncMock(return_value=chat_return)
    ) as chat_mock:
        result = await svc._generate_grounded_take(
            session,
            analysis=_analysis(),
            recommendation="buy",
            score=82,
            dupe_count=0,
            pairing_names=["Grey Chinos", "Brown Loafers"],
            compatible_count=2,
            fills_gap=True,
            new_occasions={"business casual"},
            new_seasons=set(),
            category="outerwear",
        )
    return result, chat_mock


_DOCS = [
    {"title": "Color Matching Fundamentals", "content": "Neutrals pair with anything."},
    {"title": "Business Casual Dressing Guide", "content": "Blazers elevate chinos."},
]


@pytest.mark.asyncio
async def test_take_returns_none_without_knowledge():
    """No retrieved knowledge → no take (caller keeps deterministic reasoning)."""
    result, chat_mock = await _call_take("ignored", docs=[])
    assert result is None
    chat_mock.assert_not_awaited()  # never even calls the model ungrounded


@pytest.mark.asyncio
async def test_take_is_generated_in_grounded_mode():
    payload = json.dumps({"verdict": "Strong buy — pairs with your chinos [SOURCE-2].", "cited_sources": [2]})
    result, chat_mock = await _call_take(payload, docs=_DOCS)

    assert result is not None
    assert result["grounded"] is True
    assert result["take"].startswith("Strong buy")
    assert result["cited_titles"] == ["Business Casual Dressing Guide"]

    kwargs = chat_mock.await_args.kwargs
    assert kwargs["use_json_mode"] is True
    assert kwargs["temperature"] <= 0.3
    user_msg = kwargs["messages"][0]["content"]
    assert "[VERDICT FACTS]" in user_msg
    assert "BUY (buy score 82/100)" in user_msg  # the authoritative verdict is pinned
    assert "Do not invent" in user_msg


@pytest.mark.asyncio
async def test_hallucinated_citation_numbers_are_dropped():
    """A source number the model invents (out of range) never reaches the user."""
    payload = json.dumps({"verdict": "Looks great.", "cited_sources": [99, 0, "x"]})
    result, _ = await _call_take(payload, docs=_DOCS)
    assert result is not None
    assert result["cited_titles"] == []  # all invalid refs filtered


@pytest.mark.asyncio
async def test_unparseable_or_empty_take_degrades_to_none():
    assert (await _call_take("not json at all", docs=_DOCS))[0] is None
    assert (await _call_take(json.dumps({"verdict": "  "}), docs=_DOCS))[0] is None
