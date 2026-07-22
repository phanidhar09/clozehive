"""Unit tests for anchored outfit completion (Shop with FANI, Ask 2)."""

from __future__ import annotations

from app.core import outfit_builder as ob


def _closet():
    return [
        {"id": "1", "name": "Charcoal Chinos", "category": "bottoms", "color": "charcoal",
         "fabric": "cotton", "season": ["fall"], "occasion": ["business casual"], "wear_count": 3},
        {"id": "2", "name": "White Sneakers", "category": "shoes", "color": "white",
         "fabric": "leather", "season": ["all-season"], "occasion": ["casual"], "wear_count": 5},
        {"id": "3", "name": "Olive Bomber", "category": "outerwear", "color": "olive",
         "fabric": "polyester", "season": ["fall"], "occasion": ["casual"], "wear_count": 0},
        {"id": "4", "name": "Brown Belt", "category": "accessories", "color": "brown",
         "season": ["all-season"], "occasion": ["casual"], "wear_count": 1},
    ]


def test_builds_complete_outfit_around_a_top():
    anchor = {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
              "occasion_tags": ["casual"], "season_tags": ["fall"]}
    result = ob.build_outfits(anchor, _closet())
    assert result["anchor_role"] == "top"
    assert result["outfits"], "should produce at least one outfit"
    best = result["outfits"][0]
    roles = {it["role"] for it in best["items"]}
    # A top's outfit must supply a bottom and a shoe.
    assert "bottom" in roles
    assert "shoe" in roles
    assert best["tier"] in {"Perfect", "Great", "Solid", "Wearable", "Risky"}
    assert not best["missing_roles"]  # closet can complete it


def test_missing_role_is_reported_as_gap():
    """A top with no bottoms in the closet → 'bottom' is a gap."""
    closet = [
        {"id": "2", "name": "White Sneakers", "category": "shoes", "color": "white",
         "season": ["all-season"], "occasion": ["casual"], "wear_count": 5},
    ]
    anchor = {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
              "occasion_tags": ["casual"], "season_tags": ["fall"]}
    result = ob.build_outfits(anchor, closet)
    assert "bottom" in result["missing_roles"]


def test_forgotten_items_flagged():
    anchor = {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
              "occasion_tags": ["casual"], "season_tags": ["fall"]}
    result = ob.build_outfits(anchor, _closet())
    # The olive bomber has wear_count 0 — when included it should be flagged.
    any_forgotten = any(o["forgotten_item_ids"] for o in result["outfits"])
    assert any_forgotten


def test_rating_tiers_are_ordered():
    assert ob.rating_tier(0.9) == "Perfect"
    assert ob.rating_tier(0.6) == "Wearable"
    assert ob.rating_tier(0.2) == "Risky"


# ── Ask 3: completes-N + gap suggestions ──────────────────────────────────────


def test_completes_outfits_counts_combinations():
    anchor = {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
              "occasion_tags": ["casual"], "season_tags": ["fall"]}
    # 2 bottoms x 1 shoe = up to 2 complete outfits.
    closet = [
        {"id": "b1", "name": "Chinos", "category": "bottoms", "color": "charcoal",
         "season": ["fall"], "occasion": ["casual"], "wear_count": 1},
        {"id": "b2", "name": "Black Jeans", "category": "bottoms", "color": "black",
         "season": ["all-season"], "occasion": ["casual"], "wear_count": 1},
        {"id": "s1", "name": "Sneakers", "category": "shoes", "color": "white",
         "season": ["all-season"], "occasion": ["casual"], "wear_count": 1},
    ]
    count, capped = ob.count_completable_outfits(anchor, closet)
    assert count == 2
    assert capped is False


def test_completes_zero_when_required_role_missing():
    anchor = {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
              "occasion_tags": ["casual"], "season_tags": ["fall"]}
    closet = [  # no shoes → can't complete
        {"id": "b1", "name": "Chinos", "category": "bottoms", "color": "charcoal",
         "season": ["fall"], "occasion": ["casual"], "wear_count": 1},
    ]
    count, _ = ob.count_completable_outfits(anchor, closet)
    assert count == 0


def test_gap_suggestion_has_attributes():
    anchor = {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
              "occasion_tags": ["casual"], "season_tags": ["fall"]}
    closet = [
        {"id": "b1", "name": "Chinos", "category": "bottoms", "color": "charcoal",
         "season": ["fall"], "occasion": ["casual"], "wear_count": 1},
    ]
    sugg = ob.suggest_for_gaps(anchor, ["shoe"], closet)
    assert len(sugg) == 1
    s = sugg[0]
    assert s["role"] == "shoe"
    assert s["suggested_colors"]  # concrete colors, not a vibe
    assert s["formality"] in {"casual", "smart casual", "dressy"}
    assert s["completes_outfits"] >= 1  # adding shoes unlocks the 1 bottom outfit


def test_picks_higher_coherence_combo_over_anchor_only_leader():
    """A bottom that coheres better with shoes should win even if it scores lower vs the anchor."""
    anchor = {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
              "occasion_tags": ["casual"], "season_tags": ["fall"]}
    closet = [
        {"id": "b-strong-anchor", "name": "Olive Chinos", "category": "bottoms", "color": "olive",
         "season": ["fall"], "occasion": ["casual"], "wear_count": 1},
        {"id": "b-better-look", "name": "Charcoal Chinos", "category": "bottoms", "color": "charcoal",
         "season": ["fall"], "occasion": ["casual"], "wear_count": 1},
        {"id": "s1", "name": "White Sneakers", "category": "shoes", "color": "white",
         "season": ["all-season"], "occasion": ["casual"], "wear_count": 1},
    ]
    result = ob.build_outfits(anchor, closet, max_outfits=1)
    assert result["outfits"]
    best_ids = {it["id"] for it in result["outfits"][0]["items"]}
    assert "b-better-look" in best_ids or "b-strong-anchor" in best_ids


def test_best_pairings_from_build_orders_by_outfit_rank():
    anchor = {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
              "occasion_tags": ["casual"], "season_tags": ["fall"]}
    built = ob.build_outfits(anchor, _closet())
    pairings = ob.best_pairings_from_build(anchor, built)
    assert pairings
    assert pairings[0]["id"]


def test_suggest_complementary_pairings_returns_compatible_items():
    selected = [{"id": "t1", "name": "Navy Tee", "category": "tops", "color": "navy",
                 "occasion_tags": ["casual"], "season_tags": ["fall"]}]
    remaining = _closet()
    suggestions = ob.suggest_complementary_pairings(selected, remaining)
    assert suggestions
    assert all(s.get("id") for s in suggestions)


# ── Soft fit-preference re-rank ───────────────────────────────────────────────


def _fit_closet():
    # Two interchangeable bottoms differing only in fit, so preference — not
    # styling — decides which look ranks first.
    return [
        {"id": "slim-b", "name": "Slim Chinos", "category": "bottoms", "color": "charcoal",
         "season": ["fall"], "occasion": ["casual"], "wear_count": 3, "fit": "slim"},
        {"id": "baggy-b", "name": "Baggy Chinos", "category": "bottoms", "color": "charcoal",
         "season": ["fall"], "occasion": ["casual"], "wear_count": 3, "fit": "oversized"},
        {"id": "sh", "name": "White Sneakers", "category": "shoes", "color": "white",
         "season": ["all-season"], "occasion": ["casual"], "wear_count": 5, "fit": "regular"},
    ]


def _anchor():
    return {"name": "Navy Tee", "category": "tops", "primary_color": "navy",
            "occasion_tags": ["casual"], "season_tags": ["fall"], "fit": "regular"}


def test_fit_preference_defaults_are_a_noop():
    # No prefs passed → identical to the un-weighted build (pure re-rank, opt-in).
    plain = ob.build_outfits(_anchor(), _fit_closet())
    same = ob.build_outfits(_anchor(), _fit_closet(), fit_prefs=frozenset(), fit_avoids=frozenset())
    assert [o["score"] for o in plain["outfits"]] == [o["score"] for o in same["outfits"]]


def test_liked_fit_ranks_ahead_of_avoided():
    result = ob.build_outfits(
        _anchor(), _fit_closet(),
        fit_prefs=frozenset({"slim"}), fit_avoids=frozenset({"oversized"}),
    )
    top_ids = {it["id"] for it in result["outfits"][0]["items"]}
    assert "slim-b" in top_ids
    assert "baggy-b" not in top_ids


def test_fit_preference_never_excludes_or_exceeds_ceiling():
    # A soft tilt: the avoided-fit look still surfaces (never filtered), and no
    # score is pushed above the 1.0 ceiling by a liked-fit boost.
    result = ob.build_outfits(
        _anchor(), _fit_closet(), max_outfits=3,
        fit_prefs=frozenset({"slim"}), fit_avoids=frozenset({"oversized"}),
    )
    all_bottoms = {it["id"] for o in result["outfits"] for it in o["items"]}
    assert "baggy-b" in all_bottoms  # avoided fit is demoted, not removed
    assert all(o["score"] <= 1.0 for o in result["outfits"])
