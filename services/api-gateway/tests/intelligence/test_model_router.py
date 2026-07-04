"""Tests for the pre-generation model routing decision layer.

Routing must decide on *task* signals, not raw message length: a short outfit
request escalates, a long theoretical question does not.
"""

from unittest.mock import patch

import pytest

from app.api.v1.intelligence.services import model_router as mr
from app.api.v1.intelligence.services.model_router import RouteSignals, Tier


def _ambiguous_signals() -> RouteSignals:
    """Signals that land in the arbiter band [0.30, 0.45).

    evidence(0.15) + dense_constraints(0.20) = 0.35, with a long-enough message
    so the trivial-length tiebreak does not fire.
    """
    sig = RouteSignals(
        message="I'm heading out later and could use a hand figuring this out",
        expects_outfits=False,
        closet_item_count=20,
        constraint_count=3,
    )
    assert mr._ARBITER_LOW <= mr.route(sig).score < mr._ESCALATE_THRESHOLD
    return sig


# ── Hard overrides ─────────────────────────────────────────────────────────────


def test_images_always_route_to_vision():
    d = mr.route(RouteSignals(message="ok?", has_images=True))
    assert d.tier is Tier.VISION
    assert "images_attached" in d.reasons


# ── Length is not the driver ────────────────────────────────────────────────────


def test_short_outfit_request_escalates_to_large():
    """A short but demanding outfit build should NOT be treated as trivial."""
    d = mr.route(
        RouteSignals(
            message="what should I wear to a wedding?",
            expects_outfits=True,
            closet_item_count=20,
            constraint_count=3,
        )
    )
    assert d.tier is Tier.LARGE


def test_long_theoretical_question_stays_small():
    """A long, wordy but purely informational ask should stay on the cheap tier."""
    long_msg = "I was reflecting on fabrics for a while today, " * 15 + " what is color theory?"
    d = mr.route(RouteSignals(message=long_msg, expects_outfits=False, closet_item_count=20))
    assert d.tier is Tier.SMALL


def test_trivial_chitchat_routes_small():
    d = mr.route(RouteSignals(message="is navy ok with brown?", closet_item_count=20))
    assert d.tier is Tier.SMALL


# ── Intent heuristic ────────────────────────────────────────────────────────────


def test_outfit_intent_detected():
    assert mr.looks_like_outfit_request("what should I wear to the office?")
    assert mr.looks_like_outfit_request("dress me for a date")


def test_theoretical_intent_not_outfit():
    assert not mr.looks_like_outfit_request("what is color theory?")
    assert not mr.looks_like_outfit_request("how do I wash silk?")


# ── Catalog wiring ──────────────────────────────────────────────────────────────


def test_decision_carries_model_and_budget():
    small = mr.route(RouteSignals(message="hi"))
    assert small.model
    assert small.max_tokens > 0
    assert 0.0 <= small.temperature <= 1.0


# ── LLM micro-classifier (second stage) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_arbiter_skipped_outside_ambiguous_band():
    """Confident scores must never trigger an LLM call."""
    with patch.object(mr, "_classify_complexity") as classify:
        d = await mr.route_async(RouteSignals(message="is navy ok with brown?"))
    classify.assert_not_called()
    assert d.tier is Tier.SMALL


@pytest.mark.asyncio
async def test_arbiter_skipped_for_vision():
    with patch.object(mr, "_classify_complexity") as classify:
        d = await mr.route_async(RouteSignals(message="rate this", has_images=True))
    classify.assert_not_called()
    assert d.tier is Tier.VISION


@pytest.mark.asyncio
async def test_arbiter_upgrades_ambiguous_turn_to_large():
    async def _high(_msg):
        return "high"

    with patch.object(mr, "_classify_complexity", _high):
        d = await mr.route_async(_ambiguous_signals())
    assert d.tier is Tier.LARGE
    assert any("arbiter(high)" in r for r in d.reasons)


@pytest.mark.asyncio
async def test_arbiter_keeps_ambiguous_turn_small_on_low():
    async def _low(_msg):
        return "low"

    with patch.object(mr, "_classify_complexity", _low):
        d = await mr.route_async(_ambiguous_signals())
    assert d.tier is Tier.SMALL
    assert any("arbiter(low)" in r for r in d.reasons)


@pytest.mark.asyncio
async def test_arbiter_failure_falls_back_to_deterministic():
    async def _fail(_msg):
        return None

    with patch.object(mr, "_classify_complexity", _fail):
        d = await mr.route_async(_ambiguous_signals())
    assert d.tier is Tier.SMALL  # deterministic score 0.35 < threshold
    assert "arbiter_unavailable" in d.reasons


@pytest.mark.asyncio
async def test_arbiter_disabled_by_setting():
    with patch.object(mr.settings, "model_router_arbiter_enabled", False):
        with patch.object(mr, "_classify_complexity") as classify:
            d = await mr.route_async(_ambiguous_signals())
    classify.assert_not_called()
    assert d.tier is Tier.SMALL
