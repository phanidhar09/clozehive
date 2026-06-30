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


# ── Pattern harmony ───────────────────────────────────────────────────────────


def test_solid_pairs_with_any_pattern():
    assert oc.pattern_harmony("solid", "floral")[0] == 1.0
    assert oc.pattern_harmony("plaid", None)[0] == 1.0  # missing pattern is no-risk
    assert oc.pattern_harmony("", "leopard")[0] == 1.0


def test_two_bold_patterns_clash():
    score, reason = oc.pattern_harmony("floral", "plaid")
    assert score <= 0.5
    assert reason == "two busy patterns compete"


def test_bold_with_subtle_is_fine():
    assert oc.pattern_harmony("floral shirt", "pinstripe")[0] >= 0.85
    assert oc.pattern_harmony("striped", "leopard print")[1] is None


def test_clashing_patterns_sink_an_otherwise_perfect_pairing():
    """Two neutral, same-occasion pieces that would score 'perfect' on color and
    formality must still be dragged down when both carry a loud print."""
    floral_top = {"name": "floral shirt", "category": "tops", "color": "white",
                  "pattern": "floral", "occasion": ["casual"], "season": ["summer"]}
    plaid_pants = {"name": "plaid trousers", "category": "bottoms", "color": "black",
                   "pattern": "plaid", "occasion": ["casual"], "season": ["summer"]}
    clashing = oc.score_compatibility(floral_top, plaid_pants)

    solid_pants = {**plaid_pants, "pattern": "solid"}
    clean = oc.score_compatibility(floral_top, solid_pants)

    assert clashing["breakdown"]["pattern"] < clean["breakdown"]["pattern"]
    assert clashing["score"] < clean["score"]
    assert "two busy patterns compete" in clashing["reasons"]


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


# ── Fit / silhouette ──────────────────────────────────────────────────────────


def test_fit_volume_classification():
    assert oc.fit_volume("Oversized") == 2
    assert oc.fit_volume("wide-leg") == 2
    assert oc.fit_volume("slim") == 0
    assert oc.fit_volume("tailored") == 0
    assert oc.fit_volume("regular") == 1
    assert oc.fit_volume("relaxed straight") == 2  # relaxed wins over straight
    assert oc.fit_volume(None) is None
    assert oc.fit_volume("whatever") is None  # unreadable → neutral


def test_relaxed_top_with_slim_bottom_is_balanced():
    # The user's example: balance theory says contrast is *good*, not penalized.
    top = {"category": "tops", "fit": "relaxed"}
    jeans = {"category": "bottoms", "fit": "slim"}
    score, reason = oc.silhouette_harmony(top, jeans)
    assert score == 1.0
    assert reason is None


def test_volume_on_volume_is_penalized():
    top = {"category": "tops", "fit": "oversized"}
    bottom = {"category": "bottoms", "fit": "baggy"}
    score, reason = oc.silhouette_harmony(top, bottom)
    assert score < 1.0
    assert reason is not None


def test_silhouette_neutral_when_not_top_and_bottom():
    # Proportion has no bearing on a top + its shoes.
    top = {"category": "tops", "fit": "oversized"}
    shoes = {"category": "shoes", "fit": "slim"}
    assert oc.silhouette_harmony(top, shoes) == (1.0, None)


def test_silhouette_neutral_when_fit_unknown():
    # Most legacy items have no fit — must not be punished.
    top = {"category": "tops", "color": "white"}
    jeans = {"category": "bottoms", "fit": "oversized"}
    assert oc.silhouette_harmony(top, jeans) == (1.0, None)


def test_double_volume_clash_drags_a_pairing_down():
    # Same item, two fits: the volume-on-volume version must score lower.
    top = {"name": "tee", "category": "tops", "color": "white", "occasion": ["casual"]}
    relaxed_bottom = {"name": "trousers", "category": "bottoms", "color": "black",
                      "occasion": ["casual"], "fit": "baggy"}
    slim_bottom = {**relaxed_bottom, "fit": "slim"}
    oversized_top = {**top, "fit": "oversized"}
    clash = oc.score_compatibility(oversized_top, relaxed_bottom)
    balanced = oc.score_compatibility(oversized_top, slim_bottom)
    assert clash["score"] < balanced["score"]
    assert "silhouette" in clash["breakdown"]
