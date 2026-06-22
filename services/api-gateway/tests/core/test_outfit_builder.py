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
