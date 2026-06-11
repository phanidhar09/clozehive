"""Tests for chat trend grounding (Phase 7 — live, trend-intent only)."""

from datetime import date

import pytest

from app.api.v1.intelligence.services import trend_grounding as tg


# ── Intent detection ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "What's trending this summer?",
    "Are skinny jeans still in style?",
    "what is currently popular for office wear",
    "Show me the latest fashion looks",
    "is double denim out of fashion?",
    "What did people wear at fashion week?",
])
def test_trend_intent_detected(message):
    assert tg.is_trend_query(message) is True


@pytest.mark.parametrize("message", [
    "What should I wear to a wedding?",
    "Build me an outfit for tomorrow",
    "Does this shirt go with my blue chinos?",
    "Pack me for a week in Rome",
    "",
])
def test_non_trend_messages_skipped(message):
    assert tg.is_trend_query(message) is False


# ── Season partitioning ───────────────────────────────────────────────────────

def test_seasons():
    assert tg._season(date(2026, 1, 15)) == "winter"
    assert tg._season(date(2026, 4, 1)) == "spring"
    assert tg._season(date(2026, 7, 4)) == "summer"
    assert tg._season(date(2026, 10, 31)) == "fall"
    assert tg._season(date(2026, 12, 25)) == "winter"


# ── get_trend_context ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_trend_message_never_searches(monkeypatch):
    async def explode(*a, **kw):
        raise AssertionError("non-trend messages must not trigger a web call")

    monkeypatch.setattr(tg.web_intelligence, "cached_search", explode)
    assert await tg.get_trend_context("Build me a work outfit") is None


@pytest.mark.asyncio
async def test_trend_message_searches_with_season_keyed_cache(monkeypatch):
    captured = {}

    async def fake_search(query, **kw):
        captured["query"] = query
        captured["kw"] = kw
        return {"answer": "Butter yellow and wide-leg silhouettes.", "sources": [], "fetched_at": "now"}

    monkeypatch.setattr(tg.web_intelligence, "cached_search", fake_search)
    result = await tg.get_trend_context("What's trending this summer?", today=date(2026, 7, 1))
    assert result["answer"].startswith("Butter yellow")
    assert "summer 2026" in captured["query"]
    assert captured["kw"]["namespace"] == "trends"
    assert captured["kw"]["key"].startswith("summer-2026:")
    assert captured["kw"]["key"] == "summer-2026:whats trending this summer"
    assert captured["kw"]["ttl_seconds"] == tg.TREND_TTL_S


@pytest.mark.asyncio
async def test_web_unavailable_returns_none(monkeypatch):
    async def none_search(*a, **kw):
        return None

    monkeypatch.setattr(tg.web_intelligence, "cached_search", none_search)
    assert await tg.get_trend_context("what's trending now?") is None


# ── Prompt block ──────────────────────────────────────────────────────────────

def test_block_has_answer_sources_and_closet_guardrail():
    block = tg.build_trend_block({
        "answer": "Suede is everywhere this fall.",
        "sources": [{"title": "Vogue", "url": "https://x"}],
        "fetched_at": "now",
    })
    assert "Suede is everywhere" in block
    assert "Sources: Vogue" in block
    # The closet-grounding contract must survive trend context.
    assert "ONLY items that exist in the user's wardrobe" in block
    assert "never invent items" in block
    assert block.endswith("[END CURRENT FASHION TRENDS]")


def test_none_builds_empty_block():
    assert tg.build_trend_block(None) == ""
