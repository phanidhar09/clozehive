"""Unit tests for the semantic response cache.

Hermetic: the Redis-backed cache_service.get/set are replaced with an in-memory
dict, so these tests exercise the matching/invalidation logic only.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core import semantic_cache

RESPONSE = {"reply": "Wear the navy chinos.", "recommended_outfits": []}
EMB_A = [1.0, 0.0, 0.0]
EMB_A_NEAR = [0.999, 0.04, 0.0]  # cosine ≈ 0.9992 — above the 0.95 threshold
EMB_B = [0.0, 1.0, 0.0]  # orthogonal — never matches


@pytest.fixture()
def fake_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    store: dict[str, Any] = {}

    async def _get(key: str):
        return store.get(key)

    async def _set(key: str, value: Any, ttl: int):
        store[key] = value
        return True

    async def _delete(key: str):
        store.pop(key, None)

    monkeypatch.setattr(semantic_cache.cache_service, "get", _get)
    monkeypatch.setattr(semantic_cache.cache_service, "set", _set)
    monkeypatch.setattr(semantic_cache.cache_service, "delete", _delete)
    monkeypatch.setattr(semantic_cache.settings, "semantic_cache_enabled", True)
    return store


async def _store_default(**overrides: Any) -> None:
    kwargs: dict[str, Any] = {
        "closet_hash": "closet1",
        "profile_hash": "profile1",
        "weather_key": "sunny",
    }
    kwargs.update(overrides)
    await semantic_cache.store("user1", EMB_A, RESPONSE, **kwargs)


@pytest.mark.asyncio
async def test_near_identical_embedding_hits(fake_store):
    await _store_default()
    hit = await semantic_cache.lookup(
        "user1", EMB_A_NEAR, closet_hash="closet1", profile_hash="profile1", weather_key="sunny"
    )
    assert hit == RESPONSE


@pytest.mark.asyncio
async def test_dissimilar_embedding_misses(fake_store):
    await _store_default()
    miss = await semantic_cache.lookup(
        "user1", EMB_B, closet_hash="closet1", profile_hash="profile1", weather_key="sunny"
    )
    assert miss is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,changed",
    [
        ("closet_hash", "closet2"),  # closet edited
        ("profile_hash", "profile2"),  # style profile changed
        ("weather_key", "rain"),  # different forecast
    ],
)
async def test_context_change_invalidates(fake_store, field: str, changed: str):
    await _store_default()
    kwargs = {"closet_hash": "closet1", "profile_hash": "profile1", "weather_key": "sunny"}
    kwargs[field] = changed
    assert await semantic_cache.lookup("user1", EMB_A, **kwargs) is None


@pytest.mark.asyncio
async def test_scoped_per_user(fake_store):
    await _store_default()
    other = await semantic_cache.lookup(
        "user2", EMB_A, closet_hash="closet1", profile_hash="profile1", weather_key="sunny"
    )
    assert other is None


@pytest.mark.asyncio
async def test_entry_list_pruned_to_max(fake_store, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(semantic_cache.settings, "semantic_cache_max_entries", 3)
    for i in range(5):
        await semantic_cache.store("user1", [float(i), 1.0, 0.0], {"reply": f"r{i}"}, closet_hash="c", profile_hash="p")
    entries = fake_store[semantic_cache._key("user1")]
    assert len(entries) == 3
    # Newest first
    assert entries[0]["response"]["reply"] == "r4"


@pytest.mark.asyncio
async def test_disabled_cache_is_inert(fake_store, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(semantic_cache.settings, "semantic_cache_enabled", False)
    await _store_default()
    assert fake_store == {}
    assert (
        await semantic_cache.lookup("user1", EMB_A, closet_hash="closet1", profile_hash="profile1", weather_key="sunny")
        is None
    )


@pytest.mark.asyncio
async def test_missing_embedding_is_inert(fake_store):
    await semantic_cache.store("user1", None, RESPONSE, closet_hash="c", profile_hash="p")
    assert fake_store == {}
    assert await semantic_cache.lookup("user1", None, closet_hash="c", profile_hash="p") is None


@pytest.mark.asyncio
async def test_invalidate_drops_user_entries(fake_store):
    await _store_default()
    await semantic_cache.invalidate("user1")
    assert (
        await semantic_cache.lookup("user1", EMB_A, closet_hash="closet1", profile_hash="profile1", weather_key="sunny")
        is None
    )


@pytest.mark.asyncio
async def test_backend_failure_never_raises(monkeypatch: pytest.MonkeyPatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(semantic_cache.cache_service, "get", _boom)
    monkeypatch.setattr(semantic_cache.cache_service, "set", _boom)
    monkeypatch.setattr(semantic_cache.settings, "semantic_cache_enabled", True)
    # Neither direction may break the chat path.
    assert await semantic_cache.lookup("u", EMB_A, closet_hash="c", profile_hash="p") is None
    await semantic_cache.store("u", EMB_A, RESPONSE, closet_hash="c", profile_hash="p")
