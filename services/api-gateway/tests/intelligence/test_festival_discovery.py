"""Tests for festival discovery (Phase 3 — static-first, Tavily fallback)."""

from datetime import date

import pytest

from app.api.v1.intelligence.services import festival_discovery as fd


_LIVE = {
    "answer": "The Reykjavik Culture Night takes place on 2026-08-22; locals dress warmly in smart-casual layers.",
    "sources": [{"title": "Visit Iceland", "url": "https://x"}],
    "fetched_at": "now",
}


# ── get_trip_festivals resolution order ───────────────────────────────────────

@pytest.mark.asyncio
async def test_static_hit_never_calls_web(monkeypatch):
    async def explode(*a, **kw):
        raise AssertionError("static hits must not trigger a web call")

    monkeypatch.setattr(fd.web_intelligence, "cached_search", explode)
    # Diwali (static, 2026-11-08) falls inside this Jaipur trip.
    result = await fd.get_trip_festivals("Jaipur, India", date(2026, 11, 5), date(2026, 11, 10))
    assert result["source"] == "static"
    assert result["festivals"][0]["name"] == "Diwali"
    assert result["festivals"][0]["date"] == "2026-11-08"
    assert result["live"] is None


@pytest.mark.asyncio
async def test_live_fallback_when_static_empty(monkeypatch):
    captured = {}

    async def fake_search(query, **kw):
        captured["query"] = query
        captured["namespace"] = kw["namespace"]
        captured["key"] = kw["key"]
        return _LIVE

    monkeypatch.setattr(fd.web_intelligence, "cached_search", fake_search)
    result = await fd.get_trip_festivals("Reykjavik", date(2026, 8, 20), date(2026, 8, 25))
    assert result["source"] == "live"
    assert result["live"]["answer"].startswith("The Reykjavik Culture Night")
    assert "Reykjavik" in captured["query"]
    assert "2026-08-20" in captured["query"]
    assert captured["namespace"] == "festivals"
    assert captured["key"] == "Reykjavik:2026-08-20:2026-08-25"


@pytest.mark.asyncio
async def test_no_static_no_live_returns_empty(monkeypatch):
    async def none_search(*a, **kw):
        return None

    monkeypatch.setattr(fd.web_intelligence, "cached_search", none_search)
    result = await fd.get_trip_festivals("Reykjavik", date(2026, 8, 20), date(2026, 8, 25))
    assert result == {"source": None, "festivals": [], "live": None}


@pytest.mark.asyncio
async def test_empty_destination_short_circuits(monkeypatch):
    async def explode(*a, **kw):
        raise AssertionError("must not search for an empty destination")

    monkeypatch.setattr(fd.web_intelligence, "cached_search", explode)
    result = await fd.get_trip_festivals("", date(2026, 8, 20), date(2026, 8, 25))
    assert result["source"] is None


# ── Prompt block ──────────────────────────────────────────────────────────────

def test_static_block_lists_festival_and_dress():
    result = {
        "source": "static",
        "festivals": [{
            "name": "Diwali", "emoji": "🪔", "date": "2026-11-08",
            "occasion": "festive ethnic celebration",
            "dress": "traditional ethnic wear in jewel tones; embellished fabrics, gold accents.",
        }],
        "live": None,
    }
    block = fd.build_trip_festival_block(result)
    assert "Diwali" in block and "2026-11-08" in block
    assert "jewel tones" in block
    assert block.startswith("[FESTIVALS DURING THE TRIP]")
    assert block.endswith("[END FESTIVALS]")


def test_live_block_includes_answer_sources_and_guardrail():
    block = fd.build_trip_festival_block({"source": "live", "festivals": [], "live": _LIVE})
    assert "LIVE WEB RESEARCH" in block
    assert "Reykjavik Culture Night" in block
    assert "Sources: Visit Iceland" in block
    # Guardrail: noisy live text must be ignorable by the model.
    assert "ignore this section" in block


def test_empty_result_builds_empty_block():
    assert fd.build_trip_festival_block({"source": None, "festivals": [], "live": None}) == ""


# ── Nudge context ─────────────────────────────────────────────────────────────

def test_nudge_context_static_names_festival():
    result = {
        "source": "static",
        "festivals": [{
            "name": "Diwali", "emoji": "🪔", "date": "2026-11-08",
            "occasion": "festive ethnic celebration", "dress": "jewel tones.",
        }],
        "live": None,
    }
    ctx = fd.nudge_festival_context(result)
    assert "Diwali" in ctx and "2026-11-08" in ctx


def test_nudge_context_live_has_guardrail():
    ctx = fd.nudge_festival_context({"source": "live", "festivals": [], "live": _LIVE})
    assert "Reykjavik Culture Night" in ctx
    assert "otherwise write a normal packing-prep nudge" in ctx


def test_nudge_context_empty():
    assert fd.nudge_festival_context({"source": None, "festivals": [], "live": None}) == ""
