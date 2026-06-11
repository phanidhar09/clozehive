"""Tests for Phase 1 (web_intelligence Tavily wrapper) and Phase 2 (live
destination dress guidelines in location_intel_service).

The contract under test: curated > live web > LLM-infer, and the web layer can
never break a request — every failure path degrades to the static behaviour.
"""

from types import SimpleNamespace

import pytest

from app.core import web_intelligence
from app.api.v1.travel.services import location_intel_service as lis


# ── Helpers ───────────────────────────────────────────────────────────────────

class FakeCache:
    """In-memory stand-in for app.core.cache_service get/set."""

    def __init__(self):
        self.store: dict = {}
        self.set_calls: list = []

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl):
        self.store[key] = value
        self.set_calls.append((key, value, ttl))
        return True


@pytest.fixture
def fake_cache(monkeypatch):
    cache = FakeCache()
    monkeypatch.setattr(web_intelligence.cache_service, "get", cache.get)
    monkeypatch.setattr(web_intelligence.cache_service, "set", cache.set)
    return cache


def _settings_with_key(key: str):
    return lambda: SimpleNamespace(tavily_api_key=key)


# ── web_intelligence (Phase 1) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cached_search_disabled_without_api_key(monkeypatch, fake_cache):
    monkeypatch.setattr(web_intelligence, "get_settings", _settings_with_key(""))
    result = await web_intelligence.cached_search(
        "q", namespace="t", key="x", ttl_seconds=60
    )
    assert result is None
    assert fake_cache.set_calls == []  # disabled layer must not touch the cache


@pytest.mark.asyncio
async def test_cached_search_returns_cache_hit_without_network(monkeypatch, fake_cache):
    monkeypatch.setattr(web_intelligence, "get_settings", _settings_with_key("tvly-x"))

    async def explode(*a, **kw):
        raise AssertionError("network must not be hit on cache hit")

    monkeypatch.setattr(web_intelligence, "_tavily_search", explode)
    ck = web_intelligence._cache_key("t", "Paris")
    fake_cache.store[ck] = {"answer": "cached", "sources": [], "fetched_at": "now"}

    result = await web_intelligence.cached_search(
        "q", namespace="t", key="Paris", ttl_seconds=60
    )
    assert result["answer"] == "cached"


@pytest.mark.asyncio
async def test_cached_search_negative_caches_failures(monkeypatch, fake_cache):
    monkeypatch.setattr(web_intelligence, "get_settings", _settings_with_key("tvly-x"))

    calls = {"n": 0}

    async def fail(*a, **kw):
        calls["n"] += 1
        return None

    monkeypatch.setattr(web_intelligence, "_tavily_search", fail)

    assert await web_intelligence.cached_search("q", namespace="t", key="x", ttl_seconds=60) is None
    # Second call must be served by the failure marker, not another fetch.
    assert await web_intelligence.cached_search("q", namespace="t", key="x", ttl_seconds=60) is None
    assert calls["n"] == 1
    # Failure marker stored with the short TTL, not the caller's TTL.
    assert fake_cache.set_calls[0][2] == web_intelligence._FAILURE_TTL_S


@pytest.mark.asyncio
async def test_cached_search_stores_success_with_caller_ttl(monkeypatch, fake_cache):
    monkeypatch.setattr(web_intelligence, "get_settings", _settings_with_key("tvly-x"))

    async def ok(*a, **kw):
        return {"answer": "wear modest clothing", "sources": [], "fetched_at": "now"}

    monkeypatch.setattr(web_intelligence, "_tavily_search", ok)
    result = await web_intelligence.cached_search(
        "q", namespace="dress", key="Kyoto", ttl_seconds=12345
    )
    assert result["answer"] == "wear modest clothing"
    assert fake_cache.set_calls[0][2] == 12345


def test_format_sources_line():
    line = web_intelligence.format_sources_line(
        {"sources": [{"title": "Travel Guide", "url": "https://x"}]}
    )
    assert line == "Sources: Travel Guide"
    assert web_intelligence.format_sources_line({"sources": []}) == ""


# ── location_intel_service async builder (Phase 2) ────────────────────────────

@pytest.mark.asyncio
async def test_curated_destination_never_calls_web(monkeypatch):
    async def explode(*a, **kw):
        raise AssertionError("curated destinations must not trigger a web call")

    monkeypatch.setattr(lis.web_intelligence, "cached_search", explode)
    block = await lis.build_location_context_block_async("Dubai", mode="travel")
    # Same deterministic content as the sync curated block.
    assert block == lis.build_location_context_block("Dubai", mode="travel")
    assert "Dress modesty" in block


@pytest.mark.asyncio
async def test_non_curated_uses_live_guidance(monkeypatch):
    async def fake_search(query, **kw):
        assert "Reykjavik" in query
        assert kw["namespace"] == "dress-guidelines"
        return {
            "answer": "Dress warmly in layers; smart-casual is fine everywhere.",
            "sources": [{"title": "Iceland Travel", "url": "https://x"}],
            "fetched_at": "now",
        }

    monkeypatch.setattr(lis.web_intelligence, "cached_search", fake_search)
    block = await lis.build_location_context_block_async("Reykjavik", mode="travel")
    assert "Dress guidance (live web research)" in block
    assert "Dress warmly in layers" in block
    assert "Sources: Iceland Travel" in block
    # Constraint text still present — guidance is applied as constraints.
    assert "CONSTRAINTS" in block
    assert block.endswith("[END LOCATION PREFERENCES]")


@pytest.mark.asyncio
async def test_non_curated_falls_back_when_web_unavailable(monkeypatch):
    async def none_search(*a, **kw):
        return None

    monkeypatch.setattr(lis.web_intelligence, "cached_search", none_search)
    block = await lis.build_location_context_block_async("Reykjavik", mode="travel")
    # Identical to the existing LLM-infer fallback — never worse than before.
    assert block == lis.build_location_context_block("Reykjavik", mode="travel")
    assert "No curated profile is available" in block


@pytest.mark.asyncio
async def test_empty_destination_returns_empty(monkeypatch):
    async def explode(*a, **kw):
        raise AssertionError("must not search for an empty destination")

    monkeypatch.setattr(lis.web_intelligence, "cached_search", explode)
    assert await lis.build_location_context_block_async("", mode="travel") == ""


@pytest.mark.asyncio
async def test_daily_mode_uses_daily_header(monkeypatch):
    async def fake_search(*a, **kw):
        return {"answer": "Light layers.", "sources": [], "fetched_at": "now"}

    monkeypatch.setattr(lis.web_intelligence, "cached_search", fake_search)
    block = await lis.build_location_context_block_async("Reykjavik", mode="daily")
    assert block.startswith("[LOCAL CONTEXT]")
    assert block.endswith("[END LOCAL CONTEXT]")
