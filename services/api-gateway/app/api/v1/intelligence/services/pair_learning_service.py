"""Feedback-learning rollup: the write and read sides of ``item_pair_scores``.

This is the code that finally makes the ``/feedback`` endpoint's promise
("improves future recommendations") true. It has two jobs:

* :func:`apply_feedback_signal` — called when a user rates/wears an outfit. It turns
  the outfit into its constituent item *pairs* and reinforces each one, decaying the
  prior signal (see :mod:`app.core.pair_learning`). One ``ON CONFLICT`` upsert per
  pair, so it is race-free and cheap.
* :func:`load_affinity_map` — called by the outfit builder's caller. It reads every
  learned pair among a closet's items for one user and returns the bounded-affinity
  map the builder consumes.

All scoring math lives in :mod:`app.core.pair_learning`; this module only moves it
to and from Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core import pair_learning
from app.core.logging import get_logger
from app.models.learning import ItemPairScore

logger = get_logger("pair_learning_service")

# The ON CONFLICT upsert is expressed once and rendered for whichever backend is
# bound — Postgres in production, SQLite under the test suite. Both dialects accept
# ``index_elements`` matching the unique constraint's columns.
_CONFLICT_COLS = ["user_id", "item_a", "item_b"]


def _insert_for(session: AsyncSession):
    """Pick the dialect-specific ``insert`` builder so ON CONFLICT compiles anywhere."""
    bind = session.bind
    name = bind.dialect.name if bind is not None else "postgresql"
    return sqlite_insert if name == "sqlite" else pg_insert


def signal_weight(rating: int | None, was_worn: bool) -> float:
    """Collapse a feedback event's fields into one signed reinforcement weight.

    A star rating maps through :func:`pair_learning.rating_weight` (5★ positive,
    1★ negative); wearing the look adds a passive positive on top. Returns 0.0 when
    the event carries no usable signal, letting the caller skip the write entirely.
    """
    weight = pair_learning.rating_weight(rating)
    if was_worn:
        weight += pair_learning.WEAR_WEIGHT
    return weight


def _valid_uuids(item_ids: list[str]) -> list[str]:
    """Keep only well-formed uuid strings, de-duplicated, order-stable.

    Feedback payloads are user-supplied; a malformed id would blow up the FK insert,
    so we filter defensively rather than trust the request.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in item_ids:
        s = str(raw)
        if s in seen:
            continue
        try:
            uuid.UUID(s)
        except ValueError:
            continue
        seen.add(s)
        out.append(s)
    return out


async def apply_feedback_signal(
    session: AsyncSession,
    user_id: str | uuid.UUID,
    item_ids: list[str],
    weight: float,
) -> int:
    """Reinforce every item pair in an outfit by ``weight``. Returns pairs updated.

    No-op (returns 0) when the weight is negligible or the outfit has fewer than two
    valid items — there is no pair to learn from. Each pair is upserted with the
    decay-then-add rule expressed directly in SQL, so concurrent feedback on the same
    pair composes correctly without a read-modify-write race.
    """
    if abs(weight) < 1e-9:
        return 0
    ids = _valid_uuids(item_ids)
    if len(ids) < 2:
        return 0

    uid = uuid.UUID(str(user_id))
    insert = _insert_for(session)
    updated = 0
    for a, b in combinations(ids, 2):
        item_a, item_b = pair_learning.canonical_pair(a, b)
        stmt = insert(ItemPairScore).values(
            id=uuid.uuid4(),
            user_id=uid,
            item_a=uuid.UUID(item_a),
            item_b=uuid.UUID(item_b),
            raw_score=weight,  # first-ever signal: decay(0) + weight == weight
            signal_count=1,
            last_signal_at=func.now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=_CONFLICT_COLS,
            set_={
                # Decay the stored accumulator, then add the new signal — the SQL
                # form of pair_learning.record_signal, evaluated atomically.
                "raw_score": ItemPairScore.raw_score * pair_learning.DECAY + weight,
                "signal_count": ItemPairScore.signal_count + 1,
                "last_signal_at": func.now(),
            },
        )
        await session.execute(stmt)
        updated += 1

    logger.info("pair_learning_signal", user_id=str(uid), pairs=updated, weight=round(weight, 3))
    return updated


async def load_affinity_map(
    session: AsyncSession,
    user_id: str | uuid.UUID,
    item_ids: list[str],
) -> dict[frozenset[str], float]:
    """Bounded-affinity map for every learned pair among ``item_ids`` for this user.

    Keyed by ``frozenset({item_a, item_b})`` so the builder can look up an unordered
    pair directly. Returns an empty map when there is nothing to score, which the
    builder treats as "no learned signal" (identical to today's ranking).
    """
    ids = _valid_uuids(item_ids)
    if len(ids) < 2:
        return {}

    uid = uuid.UUID(str(user_id))
    uid_ids = [uuid.UUID(i) for i in ids]
    result = await session.execute(
        select(ItemPairScore).where(
            ItemPairScore.user_id == uid,
            ItemPairScore.item_a.in_(uid_ids),
            ItemPairScore.item_b.in_(uid_ids),
        )
    )
    now = datetime.now(UTC)
    affinity_map: dict[frozenset[str], float] = {}
    for row in result.scalars():
        aff = pair_learning.affinity(row.raw_score, row.last_signal_at, now)
        if aff != 0.0:
            affinity_map[frozenset((str(row.item_a), str(row.item_b)))] = aff
    return affinity_map
