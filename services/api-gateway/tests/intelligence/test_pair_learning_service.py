"""DB rollup + closed-loop tests for the feedback-learning service.

Covers the write side (feedback → item_pair_scores upsert), the read side
(load_affinity_map), and the end-to-end loop through the /feedback endpoint —
proving the endpoint's "improves future recommendations" promise is now real.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.api.v1.intelligence.services import pair_learning_service as pls
from app.core import pair_learning as pl
from app.models.closet import ClosetItem
from app.models.learning import ItemPairScore


async def _closet(session, uid, n=3):
    names = [("Tee", "tops"), ("Chinos", "bottoms"), ("Loafers", "shoes"), ("Belt", "accessories")]
    items = [ClosetItem(user_id=uid, name=nm, category=cat, color="navy") for nm, cat in names[:n]]
    for it in items:
        session.add(it)
    await session.flush()
    return [str(it.id) for it in items]


# ── signal weight mapping ─────────────────────────────────────────────────────


def test_signal_weight_combines_rating_and_wear():
    assert pls.signal_weight(5, True) > pls.signal_weight(5, False)  # wearing adds
    assert pls.signal_weight(1, False) < 0  # a pan is negative
    assert pls.signal_weight(None, False) == 0  # nothing to learn


# ── write side ────────────────────────────────────────────────────────────────


async def test_apply_feedback_upserts_one_row_per_pair(db_session):
    uid = uuid.uuid4()
    ids = await _closet(db_session, uid, n=3)  # 3 items → 3 pairs

    updated = await pls.apply_feedback_signal(db_session, uid, ids, weight=0.6)
    assert updated == 3

    count = await db_session.scalar(
        select(func.count()).select_from(ItemPairScore).where(ItemPairScore.user_id == uid)
    )
    assert count == 3


async def test_repeat_feedback_decays_then_adds_same_row(db_session):
    uid = uuid.uuid4()
    ids = await _closet(db_session, uid, n=2)  # 1 pair

    await pls.apply_feedback_signal(db_session, uid, ids, weight=0.6)
    await pls.apply_feedback_signal(db_session, uid, ids, weight=0.6)

    rows = (await db_session.execute(select(ItemPairScore).where(ItemPairScore.user_id == uid))).scalars().all()
    assert len(rows) == 1  # upsert, not a second row
    assert rows[0].signal_count == 2
    assert rows[0].raw_score == pytest.approx(pl.record_signal(0.6, 0.6))


async def test_negligible_weight_and_single_item_are_noops(db_session):
    uid = uuid.uuid4()
    ids = await _closet(db_session, uid, n=2)
    assert await pls.apply_feedback_signal(db_session, uid, ids, weight=0.0) == 0
    assert await pls.apply_feedback_signal(db_session, uid, ids[:1], weight=0.6) == 0


async def test_malformed_item_ids_are_filtered(db_session):
    uid = uuid.uuid4()
    ids = await _closet(db_session, uid, n=2)
    # A junk id mixed in must not blow up the FK insert; only the valid pair lands.
    updated = await pls.apply_feedback_signal(db_session, uid, [*ids, "not-a-uuid"], weight=0.6)
    assert updated == 1


# ── read side ─────────────────────────────────────────────────────────────────


async def test_load_affinity_map_keys_and_signs(db_session):
    uid = uuid.uuid4()
    ids = await _closet(db_session, uid, n=2)

    await pls.apply_feedback_signal(db_session, uid, ids, weight=0.8)
    amap = await pls.load_affinity_map(db_session, uid, ids)

    key = frozenset((ids[0], ids[1]))
    assert key in amap
    assert amap[key] > 0  # a liked pair reads positive

    # A different user shares no signal (per-user isolation).
    assert await pls.load_affinity_map(db_session, uuid.uuid4(), ids) == {}


async def test_reject_signal_reads_negative(db_session):
    uid = uuid.uuid4()
    ids = await _closet(db_session, uid, n=2)
    await pls.apply_feedback_signal(db_session, uid, ids, weight=pls.signal_weight(1, False))
    amap = await pls.load_affinity_map(db_session, uid, ids)
    assert amap[frozenset((ids[0], ids[1]))] < 0


# ── closed loop through the endpoint ──────────────────────────────────────────


async def test_feedback_endpoint_populates_pair_scores(client, db_session, auth_headers):
    # Build a closet for the authenticated fixture user so the item ids are real.
    from app.models.user import User

    uid = (await db_session.execute(select(User.id).where(User.email == "fixture@example.com"))).scalar_one()
    ids = await _closet(db_session, uid, n=2)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/ai-chat/feedback",
        headers=auth_headers,
        json={"closet_item_ids": ids, "rating": 5, "was_worn": True},
    )
    assert resp.status_code == 201

    count = await db_session.scalar(
        select(func.count()).select_from(ItemPairScore).where(ItemPairScore.user_id == uid)
    )
    assert count == 1  # the loop closed — feedback wrote a learned pair
