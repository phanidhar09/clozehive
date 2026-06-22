"""Unit tests for the outfit compatibility engine (Shop with FANI, Ask 1).

Locks in the core distinction: embedding similarity finds duplicates, this finds
*matches*. These are pure-function tests — no DB, no network.
"""

from __future__ import annotations

from app.core import outfit_compatibility as oc


# ── Color harmony ─────────────────────────────────────────────────────────────


def test_neutral_pairs_with_anything():
    assert oc.color_harmony("black", "red")[0] == 1.0
    assert oc.color_harmony("navy blue", "burgundy")[0] == 1.0  # navy reads neutral
    assert oc.color_harmony("white", "emerald green")[0] == 1.0


def test_complementary_scores_high():
    score, reason = oc.color_harmony("blue", "orange")  # ~190° apart
    assert score >= 0.85
    assert reason == "complementary colors"


def test_clashing_colors_score_low():
    score, reason = oc.color_harmony("red", "yellow")  # ~55° apart, muddy
    assert score <= 0.4
    assert reason == "colors clash"


def test_unknown_color_is_neutralish():
    assert oc.color_harmony("chartreuse-ish", "blah")[0] == 0.6


# ── Formality ─────────────────────────────────────────────────────────────────


def test_silk_blazer_more_formal_than_joggers():
    blazer = {"name": "silk blazer", "category": "outerwear", "fabric": "silk",
              "occasion": ["business"]}
    joggers = {"name": "fleece joggers", "category": "bottoms", "fabric": "fleece",
               "occasion": ["athleisure"]}
    assert oc.formality_level(blazer) > oc.formality_level(joggers) + 1.5


def test_formality_mismatch_flagged():
    blazer = {"name": "wool blazer", "category": "outerwear", "fabric": "wool",
              "occasion": ["formal"]}
    joggers = {"name": "joggers", "category": "bottoms", "fabric": "fleece",
               "occasion": ["sport"]}
    score, reason = oc.formality_match(blazer, joggers)
    assert score < 0.4
    assert reason == "formality mismatch"


# ── Category role ─────────────────────────────────────────────────────────────


def test_top_and_bottom_pair_but_two_tops_do_not():
    assert oc.roles_pair("top", "bottom")
    assert not oc.roles_pair("top", "top")
    assert not oc.roles_pair("bottom", "bottom")


def test_dress_does_not_take_a_top_or_bottom():
    assert not oc.roles_pair("onepiece", "top")
    assert not oc.roles_pair("onepiece", "bottom")
    assert oc.roles_pair("onepiece", "shoe")
    assert oc.roles_pair("onepiece", "layer")


def test_accessory_pairs_with_everything():
    for r in ("top", "bottom", "onepiece", "layer", "shoe", "accessory"):
        assert oc.roles_pair("accessory", r)


# ── Fused compatibility: the headline behaviour ───────────────────────────────


def test_duplicate_category_is_not_a_pairing():
    """Two navy blazers are near-identical by embedding but must NOT count as a
    match — they compete for the same slot."""
    blazer_a = {"name": "navy blazer", "category": "outerwear", "color": "navy",
                "occasion": ["business"]}
    blazer_b = {"name": "navy blazer", "category": "outerwear", "color": "navy",
                "occasion": ["business"]}
    result = oc.score_compatibility(blazer_a, blazer_b)
    assert result["role_compatible"] is False
    assert result["pairs"] is False


def test_blazer_and_chinos_pair_well():
    blazer = {"name": "navy blazer", "category": "outerwear", "color": "navy",
              "fabric": "wool", "occasion": ["business"], "season": ["fall"]}
    chinos = {"name": "charcoal chinos", "category": "bottoms", "color": "charcoal",
              "fabric": "cotton", "occasion": ["business casual"], "season": ["fall"]}
    result = oc.score_compatibility(blazer, chinos)
    assert result["role_compatible"] is True
    assert result["pairs"] is True
    assert result["score"] >= oc.PAIR_THRESHOLD


def test_silk_blazer_and_gym_shorts_do_not_pair():
    blazer = {"name": "silk blazer", "category": "outerwear", "color": "black",
              "fabric": "silk", "occasion": ["formal"], "season": ["all-season"]}
    shorts = {"name": "gym shorts", "category": "bottoms", "color": "neon green",
              "fabric": "polyester", "occasion": ["gym"], "season": ["summer"]}
    result = oc.score_compatibility(blazer, shorts)
    # Role-compatible (top+bottom) but formality gulf should sink the pairing.
    assert result["role_compatible"] is True
    assert result["pairs"] is False
