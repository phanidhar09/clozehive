"""Tests for venue/event dress rules (Phase 4 — live, activity-driven)."""

from datetime import date

import pytest

from app.api.v1.travel.services import venue_rules_service as vrs


def _acts(*names: str) -> list[dict]:
    return [{"name": n} for n in names]


# ── Context selection heuristic ───────────────────────────────────────────────

def test_generic_presets_are_skipped():
    acts = _acts("Business Meeting", "Wedding / Formal", "Beach / Pool", "Airport Travel")
    assert vrs.select_rule_worthy_contexts(acts) == []


def test_specific_rule_worthy_activities_selected():
    acts = _acts("RSA Conference 2026", "Sightseeing / Walking", "Dinner at a Michelin restaurant")
    assert vrs.select_rule_worthy_contexts(acts) == [
        "RSA Conference 2026",
        "Dinner at a Michelin restaurant",
    ]


def test_non_rule_worthy_custom_activities_skipped():
    acts = _acts("Morning run by the river", "Visit grandma")
    assert vrs.select_rule_worthy_contexts(acts) == []


def test_lookup_cap_and_dedupe():
    acts = _acts(
        "Tech Summit", "tech summit",  # dupe (case-insensitive)
        "Opera night", "Embassy visa appointment",  # third rule-worthy → beyond cap
    )
    contexts = vrs.select_rule_worthy_contexts(acts)
    assert len(contexts) == vrs.MAX_LOOKUPS_PER_TRIP == 2
    assert contexts == ["Tech Summit", "Opera night"]


def test_empty_and_none_activities():
    assert vrs.select_rule_worthy_contexts(None) == []
    assert vrs.select_rule_worthy_contexts([]) == []
    assert vrs.select_rule_worthy_contexts([{"name": ""}]) == []


# ── get_venue_rules ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_rule_worthy_contexts_never_calls_web(monkeypatch):
    async def explode(*a, **kw):
        raise AssertionError("no contexts → no web call")

    monkeypatch.setattr(vrs.web_intelligence, "cached_search", explode)
    rules = await vrs.get_venue_rules(_acts("Beach / Pool"), "Dubai", date(2026, 7, 1))
    assert rules == []


@pytest.mark.asyncio
async def test_rules_fetched_per_context_with_cache_key(monkeypatch):
    captured = []

    async def fake_search(query, **kw):
        captured.append((query, kw))
        return {"answer": "Business attire required; no shorts.", "sources": [], "fetched_at": "now"}

    monkeypatch.setattr(vrs.web_intelligence, "cached_search", fake_search)
    rules = await vrs.get_venue_rules(
        _acts("RSA Conference 2026"), "San Francisco", date(2026, 4, 27)
    )
    assert len(rules) == 1
    assert rules[0]["context"] == "RSA Conference 2026"
    assert "no shorts" in rules[0]["answer"]
    query, kw = captured[0]
    assert "RSA Conference 2026" in query
    assert "San Francisco" in query and "2026" in query
    assert kw["namespace"] == "venue-rules"
    assert kw["key"] == "RSA Conference 2026:San Francisco"
    assert kw["ttl_seconds"] == vrs.VENUE_RULES_TTL_S


@pytest.mark.asyncio
async def test_web_unavailable_returns_empty(monkeypatch):
    async def none_search(*a, **kw):
        return None

    monkeypatch.setattr(vrs.web_intelligence, "cached_search", none_search)
    rules = await vrs.get_venue_rules(_acts("Tech Summit"), "Berlin", date(2026, 9, 1))
    assert rules == []


# ── Prompt block ──────────────────────────────────────────────────────────────

def test_block_frames_rules_as_mandatory_with_guardrails():
    rules = [{
        "context": "Emirates business class flight",
        "answer": "Smart casual required to board; no flip-flops or sportswear.",
        "sources": [{"title": "Emirates", "url": "https://x"}],
    }]
    block = vrs.build_venue_rules_block(rules)
    assert "Emirates business class flight" in block
    assert "no flip-flops" in block
    assert "Sources: Emirates" in block
    assert "MANDATORY" in block
    # Ranking lives centrally in constraint_priority — the block defers to it.
    assert "constraint priority" in block
    # Noisy research must be ignorable.
    assert "ignore it" in block
    assert block.endswith("[END VENUE & EVENT DRESS RULES]")


def test_empty_rules_build_empty_block():
    assert vrs.build_venue_rules_block([]) == ""
