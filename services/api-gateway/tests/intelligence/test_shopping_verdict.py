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


def test_ten_point_scale_is_derived_and_clamped():
    assert svc.to_ten_point(82) == 8.2
    assert svc.to_ten_point(100) == 10.0
    assert svc.to_ten_point(0) == 0.0
    assert svc.to_ten_point(35) == 3.5
    # Never escapes 0–10 even on out-of-range input.
    assert svc.to_ten_point(120) == 10.0
    assert svc.to_ten_point(-5) == 0.0


def test_rating_color_bands():
    """The verdict is a rating + colour, never a buy/skip word."""
    assert svc.rating_color(85) == "green"
    assert svc.rating_color(70) == "green"
    assert svc.rating_color(69) == "amber"
    assert svc.rating_color(45) == "amber"
    assert svc.rating_color(44) == "red"
    assert svc.rating_color(0) == "red"


def test_effective_weights_redistribute_without_profile():
    """No profile → style_match's weight folds into the closet-evidence factors,
    and the effective weights still sum to 100."""
    w = svc.effective_weights(has_profile=False)
    assert "style_match" not in w
    assert round(sum(w.values())) == 100
    # The closet factors each absorb a share of the 25 points.
    assert w["compatibility"] > svc._WEIGHTS["compatibility"]
    assert w["uniqueness"] > svc._WEIGHTS["uniqueness"]
    # Non-closet factors are untouched.
    assert w["gap_fill"] == svc._WEIGHTS["gap_fill"]


def test_breakdown_always_sums_to_score():
    """Whatever the inputs, the per-factor contributions sum to the buy score, and
    the returned weights sum to 100 — with or without a profile."""
    import itertools

    for has_dupe, fills_gap, occ, sea in itertools.product([True, False], repeat=4):
        for count in (0, 1, 4, 10):
            for style in (None, 0.0, 0.5, 1.0):
                score, breakdown, _, weights = svc.compute_buy_score(
                    has_duplicate=has_dupe,
                    compatible_count=count,
                    fills_gap=fills_gap,
                    has_new_occasions=occ,
                    has_new_seasons=sea,
                    style_match=style,
                )
                assert score == round(sum(breakdown.values()))
                assert 0 <= score <= 100
                assert round(sum(weights.values())) == 100
                assert set(breakdown) == set(weights)


def test_strong_unique_compatible_on_taste_item_is_a_buy():
    score, breakdown, rec, _ = svc.compute_buy_score(
        has_duplicate=False,
        compatible_count=4,  # saturates compatibility
        fills_gap=True,
        has_new_occasions=True,
        has_new_seasons=True,
        style_match=1.0,  # perfect personal fit
    )
    assert score == 100
    assert rec == "buy"
    assert breakdown["compatibility"] == 35.0
    assert breakdown["style_match"] == 25.0
    assert breakdown["uniqueness"] == 20.0


def test_off_taste_item_scores_a_full_25_lower():
    """Identical closet fit; only the personal-style match differs by its weight."""
    common = dict(
        has_duplicate=False, compatible_count=4, fills_gap=False,
        has_new_occasions=False, has_new_seasons=False,
    )
    loved = svc.compute_buy_score(**common, style_match=1.0)[0]
    hated = svc.compute_buy_score(**common, style_match=0.0)[0]
    assert loved - hated == 25


def test_duplicate_suppresses_uniqueness_and_novelty():
    """A duplicate zeroes uniqueness AND the novelty factors (no double credit)."""
    score, breakdown, rec, _ = svc.compute_buy_score(
        has_duplicate=True,
        compatible_count=4,
        fills_gap=False,
        has_new_occasions=True,  # must NOT count while it's a duplicate
        has_new_seasons=True,
        style_match=0.0,
    )
    assert breakdown["uniqueness"] == 0.0
    assert breakdown["occasion_new"] == 0.0
    assert breakdown["season_new"] == 0.0
    assert breakdown["compatibility"] == 35.0
    assert score == 35
    assert rec == "skip"


def test_recommendation_bands():
    # skip: lone gap-fill = 10
    assert svc.compute_buy_score(
        has_duplicate=True, compatible_count=0, fills_gap=True,
        has_new_occasions=False, has_new_seasons=False,
    )[2] == "skip"
    # consider (no profile): not a dupe + half compatibility, weights redistributed
    assert svc.compute_buy_score(
        has_duplicate=False, compatible_count=2, fills_gap=False,
        has_new_occasions=False, has_new_seasons=False,
    )[2] == "consider"
    # buy: uniqueness(20) + full compatibility(35) + gap(10) + full style(25) = 90
    assert svc.compute_buy_score(
        has_duplicate=False, compatible_count=4, fills_gap=True,
        has_new_occasions=False, has_new_seasons=False, style_match=1.0,
    )[2] == "buy"


# ── Personal-fit alignment (coloring / fit / taste) ──────────────────────────────


def test_style_alignment_is_none_without_usable_profile():
    assert svc.compute_style_alignment({"primary_color": "navy"}, None) == (None, [])
    empty = {"favorite_colors": [], "avoided_colors": [], "fit_preferences": [], "avoidances": []}
    assert svc.compute_style_alignment({"primary_color": "navy"}, empty)[0] is None


def test_style_alignment_favorite_color_scores_high():
    score, reasons = svc.compute_style_alignment(
        {"primary_color": "navy blue"}, {"favorite_colors": ["navy"]}
    )
    assert score == 1.0
    assert any("favorite" in r.lower() for r in reasons)


def test_style_alignment_avoided_color_scores_low():
    score, _ = svc.compute_style_alignment(
        {"primary_color": "neon green"}, {"avoided_colors": ["neon green"]}
    )
    assert score == 0.1


def test_style_alignment_averages_avoided_fit_with_loved_taste():
    score, _ = svc.compute_style_alignment(
        {"fit": "oversized", "style_tags": ["minimalist"]},
        {"fit_preferences": ["slim"], "avoidances": ["oversized"], "style_preferences": ["minimalist"]},
    )
    assert score == pytest.approx(0.55)  # avoided fit (0.1) + on-taste (1.0) → mean


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
    assert "Rating: 8.2/10 (green)" in user_msg  # rating + colour, not a buy/skip word
    assert "BUY" not in user_msg and "skip" not in user_msg.lower()
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
