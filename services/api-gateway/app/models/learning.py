"""Personalization-learning ORM models.

The feedback *signals* live elsewhere and predate this module:
``OutfitFeedback`` (rating / was_worn / closet_item_ids) in :mod:`app.models.ai_chat`
and ``WearEvent`` in :mod:`app.models.closet`. This module holds only the
*derived* rollup those signals feed — the affinity between two closet items —
which the outfit builder reads to softly re-rank looks toward pairings the user
has actually accepted or worn.

Keeping the derived layer separate from the raw signals means the rollup can be
recomputed or dropped without touching the append-only signal history.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ItemPairScore(Base):
    """Learned affinity between two of a user's closet items.

    One row per *unordered* pair, enforced by canonical ordering (``item_a`` holds
    the lexicographically smaller id) plus the unique constraint. ``raw_score`` is a
    running accumulator updated by :func:`app.core.pair_learning.record_signal` on
    each feedback event; the bounded, recency-weighted affinity the builder consumes
    is derived from it at read time via :func:`app.core.pair_learning.affinity`.
    """

    __tablename__ = "item_pair_scores"
    __table_args__ = (UniqueConstraint("user_id", "item_a", "item_b", name="uq_item_pair_scores_user_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_a: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("closet_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_b: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("closet_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_signal_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
