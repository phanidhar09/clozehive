"""Saved outfits must surface in outfit_history (the Saved Outfits page's source).

Regression tests for the store split where POST /outfits/ and
POST /ai-chat/save-outfit wrote only to the ``outfits`` table, so saved
looks never appeared on the Saved Outfits page (which lists
GET /outfits/history/).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import OutfitHistory


async def _auth_headers(client: AsyncClient, suffix: str = "") -> dict:
    resp = await client.post("/api/v1/auth/signup", json={
        "name": f"Outfit Saver{suffix}",
        "email": f"outfitsaver{suffix}@example.com",
        "username": f"outfitsaver{suffix}",
        "password": "Password1",
        "gdpr_consent": True,
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _me_id(client: AsyncClient, headers: dict) -> str:
    resp = await client.get("/api/v1/auth/me", headers=headers)
    return resp.json()["id"]


async def _create_items(client: AsyncClient, headers: dict, count: int = 2) -> list[str]:
    ids = []
    for i in range(count):
        resp = await client.post("/api/v1/closet/", json={
            "name": f"Item {i}",
            "category": "tops" if i % 2 == 0 else "bottoms",
            "color": "white",
        }, headers=headers)
        assert resp.status_code == 201
        ids.append(resp.json()["id"])
    return ids


@pytest.mark.asyncio
async def test_create_outfit_appears_in_history(client: AsyncClient):
    """POST /outfits/ must produce a was_saved outfit_history row."""
    headers = await _auth_headers(client, "1")
    item_ids = await _create_items(client, headers)

    resp = await client.post("/api/v1/outfits/", json={
        "name": "Weekend Casual",
        "item_ids": item_ids,
        "occasion": "casual",
        "notes": "Easy weekend look",
    }, headers=headers)
    assert resp.status_code == 201

    hist = await client.get("/api/v1/outfits/history/", headers=headers)
    assert hist.status_code == 200
    results = hist.json()["results"]
    assert len(results) == 1
    record = results[0]
    assert record["was_saved"] is True
    assert set(record["selected_item_ids"]) == set(item_ids)
    assert record["occasion"] == "casual"
    assert record["recommendation_text"] == "Easy weekend look"


@pytest.mark.asyncio
async def test_saving_existing_ai_look_flips_flag_without_duplicate(
    client: AsyncClient, db_session: AsyncSession
):
    """Saving an outfit whose item set already has a history row (the
    generation-time record) must flip was_saved on that row, not add one."""
    headers = await _auth_headers(client, "2")
    item_ids = await _create_items(client, headers)
    user_id = await _me_id(client, headers)

    # Simulate the generation-time history row (no embedding needed)
    db_session.add(OutfitHistory(
        user_id=uuid.UUID(user_id),
        occasion="party",
        selected_item_ids=list(reversed(item_ids)),  # order must not matter
        matching_score=80,
        recommendation_text="AI look",
        improvement_tips=[],
        was_saved=False,
    ))
    await db_session.commit()

    resp = await client.post("/api/v1/outfits/", json={
        "name": "Party Look",
        "item_ids": item_ids,
        "occasion": "party",
    }, headers=headers)
    assert resp.status_code == 201

    hist = await client.get("/api/v1/outfits/history/", headers=headers)
    results = hist.json()["results"]
    assert len(results) == 1  # flag flipped in place — no duplicate row
    assert results[0]["was_saved"] is True
    assert results[0]["matching_score"] == 80


@pytest.mark.asyncio
async def test_chat_save_outfit_appears_in_history(client: AsyncClient):
    """POST /ai-chat/save-outfit must also mirror into outfit_history."""
    headers = await _auth_headers(client, "3")
    item_ids = await _create_items(client, headers)

    resp = await client.post("/api/v1/ai-chat/save-outfit", json={
        "name": "Chat Look",
        "item_ids": item_ids,
        "occasion": "dinner",
        "explanation": "FANI's pick",
        "style_score": 91,
    }, headers=headers)
    assert resp.status_code == 201

    hist = await client.get("/api/v1/outfits/history/", headers=headers)
    results = hist.json()["results"]
    assert len(results) == 1
    record = results[0]
    assert record["was_saved"] is True
    assert record["matching_score"] == 91
    assert set(record["selected_item_ids"]) == set(item_ids)
