"""Deterministic math for the outfit feedback-learning loop.

ClozeHive collects outfit feedback (rating / was_worn) and wear history but has
never fed either back into ranking. This module is the small, pure core that turns
those signals into a bounded per-pair affinity the outfit builder can consume.

Everything here is LLM-free and side-effect-free — same ethos as
:mod:`app.core.outfit_compatibility` and the fit-preference weighting. That keeps
the loop cheap, unit-testable, and incapable of introducing a hallucination: the
learned signal only ever *reorders near-ties*, it can never invent or filter an item.

Two quantities:

* ``raw_score`` — an unbounded running accumulator stored per pair. Each new signal
  decays the old accumulator (so stale taste fades) then adds the signal's weight.
* ``affinity`` — the bounded value in ``[-1, 1]`` the builder actually reads, derived
  from ``raw_score`` at read time with a recency half-life. Never stored, so changing
  the half-life needs no backfill.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

# Signal weights. Ordered by how much evidence each carries:
#   * a wear is passive (the user wore it, but may not have chosen the pairing),
#   * an accept (high rating / saved) is an active positive choice,
#   * a reject is the strongest signal — users rarely bother, so it means something.
# `rating` is not a fixed weight: a 1..5 star maps to (r - 3) / 2 ∈ [-1, 1] and is
# then scaled by RATING_WEIGHT, so 5★ ≈ a light accept and 1★ ≈ a light reject.
WEAR_WEIGHT = 0.4
ACCEPT_WEIGHT = 0.6
REJECT_WEIGHT = -0.8
RATING_WEIGHT = 0.6

# Applied to the existing accumulator before each new signal is added, so a pair's
# score is a recency-weighted sum rather than an unbounded lifetime total. Mirrors
# the decay pattern used by comparable feedback-learning systems.
DECAY = 0.995

# Read-time recency: a pair last reinforced HALFLIFE_DAYS ago counts for half.
HALFLIFE_DAYS = 60.0


def canonical_pair(a: str, b: str) -> tuple[str, str]:
    """Order two item ids so each unordered pair maps to one stored row.

    Returns ``(item_a, item_b)`` with ``item_a <= item_b``. Callers must use this
    before reading or upserting so ``(x, y)`` and ``(y, x)`` collapse to one key.
    """
    return (a, b) if a <= b else (b, a)


def rating_weight(rating: int | None) -> float:
    """Map a 1..5 star rating to a signed signal weight, or 0.0 when unrated."""
    if rating is None:
        return 0.0
    clamped = max(1, min(5, int(rating)))
    return ((clamped - 3) / 2.0) * RATING_WEIGHT


def record_signal(prev_raw: float, weight: float) -> float:
    """Decay the existing accumulator, then add the new signal's weight.

    This is the whole update rule for ``raw_score`` — pure, so the upsert path can
    compute the new value and write it in one statement.
    """
    return prev_raw * DECAY + weight


def affinity(raw_score: float, last_signal_at: datetime, now: datetime) -> float:
    """Bounded, recency-weighted affinity in ``[-1, 1]`` for one pair.

    ``tanh`` squashes the unbounded accumulator so a pair reinforced a hundred times
    can't dominate one reinforced twice; the recency factor then fades pairs the user
    hasn't reinforced lately. A pair with no history never reaches this function —
    absent pairs are treated as neutral 0 by the builder.

    Timestamps are always written as UTC (``func.now()``); a backend that returns
    them tz-naive (e.g. SQLite) is normalised to UTC here so the subtraction is total.
    """
    if last_signal_at.tzinfo is None:
        last_signal_at = last_signal_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    age_days = max(0.0, (now - last_signal_at).total_seconds() / 86400.0)
    recency = 0.5 ** (age_days / HALFLIFE_DAYS)
    return math.tanh(raw_score) * recency
