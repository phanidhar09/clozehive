"""Unit tests for the feedback-learning math and its builder re-rank.

All deterministic and DB-free — the scoring core and the bounded builder tilt.
The DB rollup (upsert + affinity load) and the closed loop through the endpoint
are covered in tests/intelligence/test_pair_learning_service.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core import outfit_builder as ob
from app.core import pair_learning as pl

# ── scoring core ──────────────────────────────────────────────────────────────


def test_canonical_pair_is_order_independent():
    assert pl.canonical_pair("b", "a") == pl.canonical_pair("a", "b") == ("a", "b")


def test_rating_weight_signs():
    assert pl.rating_weight(5) > 0  # loved → positive
    assert pl.rating_weight(1) < 0  # hated → negative
    assert pl.rating_weight(3) == 0  # neutral
    assert pl.rating_weight(None) == 0  # unrated → no signal


def test_record_signal_decays_then_adds():
    # A fresh pair just takes the weight (decay of 0 is 0).
    assert pl.record_signal(0.0, 0.6) == 0.6
    # An existing accumulator is decayed before the new weight lands.
    assert pl.record_signal(1.0, 0.6) == 1.0 * pl.DECAY + 0.6


def test_affinity_is_bounded_and_fades_with_age():
    now = datetime.now(UTC)
    fresh = pl.affinity(5.0, now, now)
    assert 0.0 < fresh <= 1.0  # tanh keeps a huge accumulator inside [-1, 1]

    stale = pl.affinity(5.0, now - timedelta(days=pl.HALFLIFE_DAYS), now)
    assert stale < fresh
    assert abs(stale - fresh * 0.5) < 1e-6  # one half-life ⇒ exactly half


def test_affinity_negative_for_disliked_pairs():
    now = datetime.now(UTC)
    assert pl.affinity(-2.0, now, now) < 0


# ── builder re-rank factor ────────────────────────────────────────────────────


def _items(*ids):
    return [{"id": i} for i in ids]


def test_factor_neutral_when_no_signal():
    items = _items("1", "2", "3")
    assert ob._pair_learning_factor(items, {}) == 1.0  # cold start
    # A pair with no matching key contributes 0 → neutral.
    assert ob._pair_learning_factor(items, {frozenset(("9", "8")): 1.0}) == 1.0


def test_factor_bounds_are_symmetric():
    items = _items("1", "2")
    pair = frozenset(("1", "2"))
    assert ob._pair_learning_factor(items, {pair: 1.0}) == 1.0 + ob._PAIR_LEARNING_BAND
    assert ob._pair_learning_factor(items, {pair: -1.0}) == 1.0 - ob._PAIR_LEARNING_BAND


def test_factor_averages_over_pairs():
    items = _items("1", "2", "3")  # three pairs
    # One strongly-liked pair, two unknown → mean affinity = 1/3.
    factor = ob._pair_learning_factor(items, {frozenset(("1", "2")): 1.0})
    assert abs(factor - (1.0 + ob._PAIR_LEARNING_BAND / 3)) < 1e-9


# ── builder integration ───────────────────────────────────────────────────────


def _closet():
    return [
        {"id": "1", "name": "Charcoal Chinos", "category": "bottoms", "color": "charcoal",
         "occasion": ["business casual"], "season": ["fall"], "wear_count": 3},
        {"id": "2", "name": "White Sneakers", "category": "shoes", "color": "white",
         "occasion": ["casual"], "season": ["all-season"], "wear_count": 5},
        {"id": "3", "name": "Blue Jeans", "category": "bottoms", "color": "blue",
         "occasion": ["casual"], "season": ["all-season"], "wear_count": 2},
        {"id": "4", "name": "Brown Loafers", "category": "shoes", "color": "brown",
         "occasion": ["business casual"], "season": ["all-season"], "wear_count": 1},
    ]


def _anchor():
    return {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
            "occasion_tags": ["casual"], "season_tags": ["fall"]}


def test_empty_affinity_matches_none():
    """A cold-start user (no signal) gets byte-identical ranking to today."""
    base = ob.build_outfits(_anchor(), _closet())
    empty = ob.build_outfits(_anchor(), _closet(), pair_affinity={})
    assert [o["items"] for o in base["outfits"]] == [o["items"] for o in empty["outfits"]]
    assert [o["score"] for o in base["outfits"]] == [o["score"] for o in empty["outfits"]]


def test_positive_signal_raises_a_looks_score_without_breaking_tiers():
    base = ob.build_outfits(_anchor(), _closet())
    top = base["outfits"][0]
    ids = [it["id"] for it in top["items"]]
    # Reinforce every pair among the top look's owned pieces + anchor.
    liked = {frozenset((a, b)) for i, a in enumerate(ids) for b in ids[i + 1 :]}
    affinity = {pair: 1.0 for pair in liked}

    boosted = ob.build_outfits(_anchor(), _closet(), pair_affinity=affinity)
    boosted_same = next(o for o in boosted["outfits"] if [it["id"] for it in o["items"]] == ids)
    assert boosted_same["score"] >= top["score"]  # tilted up (or already maxed)
    assert boosted_same["score"] <= 1.0  # clamp holds — can't exceed the top tier


def test_negative_signal_demotes_a_look():
    base = ob.build_outfits(_anchor(), _closet())
    top = base["outfits"][0]
    ids = [it["id"] for it in top["items"]]
    disliked = {frozenset((a, b)) for i, a in enumerate(ids) for b in ids[i + 1 :]}
    affinity = {pair: -1.0 for pair in disliked}

    demoted = ob.build_outfits(_anchor(), _closet(), pair_affinity=affinity)
    demoted_same = next(o for o in demoted["outfits"] if [it["id"] for it in o["items"]] == ids)
    assert demoted_same["score"] < top["score"]  # penalised, never zeroed
    assert demoted_same["score"] > 0
