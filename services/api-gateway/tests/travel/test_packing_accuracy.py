"""
Accuracy eval harness for the travel packing planner.

These tests exercise the *deterministic* accuracy machinery of
``packing_service`` — closet-grounding and trip-relevance ranking — without
calling the LLM. They double as a scored eval: each scenario contributes to an
aggregate grounding-rate / weather-fit score that is asserted against a
threshold, so a regression in the heuristics fails CI.
"""

from __future__ import annotations

from typing import Any

from app.api.v1.travel.services import packing_service as ps

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _item(item_id: str, name: str, category: str, **extra: Any) -> dict[str, Any]:
    return {"id": item_id, "name": name, "category": category, **extra}


def _big_closet() -> list[dict[str, Any]]:
    """A 50+ item wardrobe spanning seasons and categories (forces ranking)."""
    items: list[dict[str, Any]] = []
    for i in range(14):
        items.append(_item(f"sumtop{i}", f"Linen Tee {i}", "tops", season=["summer"], occasion=["casual"]))
    for i in range(14):
        items.append(_item(f"wintop{i}", f"Wool Sweater {i}", "tops", season=["winter"], occasion=["casual"]))
    for i in range(8):
        items.append(_item(f"short{i}", f"Chino Shorts {i}", "bottoms", season=["summer"]))
    for i in range(8):
        items.append(_item(f"jean{i}", f"Heavy Jeans {i}", "bottoms", season=["winter"]))
    for i in range(6):
        items.append(_item(f"sandal{i}", f"Sandals {i}", "shoes", season=["summer"]))
    for i in range(6):
        items.append(_item(f"boot{i}", f"Snow Boots {i}", "shoes", season=["winter"]))
    items.append(_item("coat1", "Rain Jacket", "outerwear", season=["all"], tags=["waterproof"]))
    return items


# ── Grounding ──────────────────────────────────────────────────────────────────


def test_grounding_downgrades_hallucinated_item():
    closet = [_item("real-1", "Blue Oxford Shirt", "tops")]
    day_plans = [
        {
            "outfits": [
                {
                    "items": [
                        {
                            "closet_item_id": "real-1",
                            "item_name": "Blue Oxford Shirt",
                            "category": "tops",
                            "source": "from_closet",
                        },
                        {
                            "closet_item_id": "ghost-9",
                            "item_name": "Designer Trench Coat",
                            "category": "outerwear",
                            "source": "from_closet",
                        },
                    ]
                }
            ]
        }
    ]
    grounded, corrected = ps._ground_day_plans_to_closet(day_plans, closet)
    items = grounded[0]["outfits"][0]["items"]
    assert corrected == 1
    # Real item untouched
    assert items[0]["source"] == "from_closet"
    assert items[0]["closet_item_id"] == "real-1"
    # Hallucinated item downgraded + id cleared
    assert items[1]["source"] == "missing_recommended"
    assert items[1]["closet_item_id"] is None


def test_grounding_repairs_wrong_id_via_name_match():
    """Model kept the right name but invented/blanked the id — we back-fill it."""
    closet = [_item("real-42", "Black Ankle Boots", "shoes")]
    day_plans = [
        {
            "outfits": [
                {
                    "items": [
                        {
                            "closet_item_id": "",
                            "item_name": "Black Ankle Boots",
                            "category": "shoes",
                            "source": "from_closet",
                        },
                    ]
                }
            ]
        }
    ]
    grounded, corrected = ps._ground_day_plans_to_closet(day_plans, closet)
    item = grounded[0]["outfits"][0]["items"][0]
    assert corrected == 1
    assert item["closet_item_id"] == "real-42"
    assert item["source"] == "from_closet"


def test_grounding_backfills_canonical_name_for_valid_id():
    """Valid id paired with an invented name — display name must come from the closet."""
    closet = [_item("real-7", "Grey Merino Crewneck", "tops")]
    day_plans = [
        {
            "outfits": [
                {
                    "items": [
                        {
                            "closet_item_id": "real-7",
                            "item_name": "Cashmere Designer Sweater",
                            "category": "tops",
                            "source": "from_closet",
                        },
                    ]
                }
            ]
        }
    ]
    grounded, corrected = ps._ground_day_plans_to_closet(day_plans, closet)
    item = grounded[0]["outfits"][0]["items"][0]
    assert corrected == 1
    assert item["item_name"] == "Grey Merino Crewneck"
    assert item["source"] == "from_closet"


def test_grounding_name_match_survives_punctuation_noise():
    closet = [_item("real-3", "Levi's 501 Jeans", "bottoms")]
    day_plans = [
        {
            "outfits": [
                {
                    "items": [
                        {
                            "closet_item_id": "",
                            "item_name": "levis 501 jeans",
                            "category": "bottoms",
                            "source": "from_closet",
                        },
                    ]
                }
            ]
        }
    ]
    grounded, _ = ps._ground_day_plans_to_closet(day_plans, closet)
    item = grounded[0]["outfits"][0]["items"][0]
    assert item["closet_item_id"] == "real-3"
    assert item["source"] == "from_closet"


def test_rewear_strategy_drops_invented_items():
    closet = [_item("real-1", "White Sneakers", "shoes")]
    rewear = [
        {"item_name": "White Sneakers", "closet_item_id": "real-1", "worn_on_days": ["Day 1", "Day 2"]},
        {"item_name": "Imaginary Loafers", "closet_item_id": "ghost-1", "worn_on_days": ["Day 3"]},
    ]
    grounded, corrected = ps._ground_rewear_strategy(rewear, closet)
    assert [e["item_name"] for e in grounded] == ["White Sneakers"]
    assert corrected == 1


def test_rewear_strategy_repairs_id_via_name():
    closet = [_item("real-9", "Denim Jacket", "outerwear")]
    rewear = [{"item_name": "Denim Jacket", "closet_item_id": None, "worn_on_days": ["Day 1"]}]
    grounded, corrected = ps._ground_rewear_strategy(rewear, closet)
    assert grounded[0]["closet_item_id"] == "real-9"
    assert corrected == 1


def test_missing_items_already_owned_are_dropped():
    """Inverse hallucination: never tell the user to buy what they own."""
    closet = [_item("real-1", "Rain Jacket", "outerwear")]
    missing = [
        {"item_name": "Rain Jacket", "category": "outerwear", "priority": "essential"},
        {"item_name": "Hiking Boots", "category": "shoes", "priority": "essential"},
    ]
    kept, dropped = ps._filter_owned_from_missing(missing, closet)
    assert dropped == 1
    assert [m["item_name"] for m in kept] == ["Hiking Boots"]


def test_bag_capacity_is_computed_not_self_reported():
    """packing_status/total_unique_items derive from the actual plan, not the LLM."""
    bag = ps.BAG_CONSTRAINTS["backpack"]  # max_tops=3, max_shoes=1
    day_plans = [
        {
            "outfits": [
                {
                    "items": [
                        {
                            "closet_item_id": f"t{i}",
                            "item_name": f"Tee {i}",
                            "category": "tops",
                            "source": "from_closet",
                        }
                        for i in range(4)  # 4 unique tops > backpack max of 3
                    ]
                }
            ]
        }
    ]
    llm_claim = {"packing_status": "fits", "total_unique_items": 1, "optimization_notes": ["roll your clothes"]}
    summary = ps._compute_bag_capacity_summary(day_plans, bag, llm_claim)
    assert summary["packing_status"] == "overpacked"
    assert summary["total_unique_items"] == 4
    assert summary["optimization_notes"] == ["roll your clothes"]


def test_grounding_leaves_missing_recommended_alone():
    closet = [_item("real-1", "Tee", "tops")]
    day_plans = [
        {
            "outfits": [
                {
                    "items": [
                        {
                            "closet_item_id": None,
                            "item_name": "Buy: Swim Trunks",
                            "category": "bottoms",
                            "source": "missing_recommended",
                        },
                    ]
                }
            ]
        }
    ]
    grounded, corrected = ps._ground_day_plans_to_closet(day_plans, closet)
    assert corrected == 0
    assert grounded[0]["outfits"][0]["items"][0]["source"] == "missing_recommended"


# ── Legacy sections derived from the rich plan ─────────────────────────────────


def test_legacy_sections_derived_from_grounded_plan():
    """take_from/still_need come from the grounded plan — no second LLM call."""
    day_plans = [
        {
            "day_number": 1,
            "outfits": [
                {
                    "activity": "Sightseeing",
                    "items": [
                        {"closet_item_id": "t1", "item_name": "Linen Tee", "category": "tops", "source": "from_closet"},
                        {
                            "closet_item_id": None,
                            "item_name": "Sun Hat",
                            "category": "accessories",
                            "source": "missing_recommended",
                        },
                    ],
                }
            ],
        },
        {
            "day_number": 2,
            "outfits": [
                {
                    "activity": "Dinner",
                    "items": [
                        {"closet_item_id": "t1", "item_name": "Linen Tee", "category": "tops", "source": "from_closet"},
                    ],
                }
            ],
        },
    ]
    missing = [{"item_name": "Sun Hat", "category": "accessories", "reason": "UV protection"}]
    take, need = ps._derive_legacy_sections(day_plans, missing)

    assert len(take) == 1
    assert take[0]["item_id"] == "t1"
    assert take[0]["recommended_days"] == ["Day 1", "Day 2"]
    # Sun Hat appears once (deduped between missing_items and the day plan) and
    # never in take_from_your_closet.
    assert [n["name"] for n in need] == ["Sun Hat"]


# ── Relevance ranking ──────────────────────────────────────────────────────────


def test_small_closet_passes_through_untrimmed():
    closet = [_item(f"i{i}", f"Item {i}", "tops") for i in range(10)]
    weather = {"avg_high": 25, "rainy_days": 0}
    ranked = ps._rank_closet_for_trip(closet, weather, [], "leisure", None, ps.BAG_CONSTRAINTS["none"])
    assert ranked == closet


def test_ranking_favours_weather_appropriate_items():
    closet = _big_closet()
    hot = {"avg_high": 32, "rainy_days": 0}
    ranked = ps._rank_closet_for_trip(closet, hot, [], "beach", "beach", ps.BAG_CONSTRAINTS["carry_on"])
    names = " ".join(i["name"] for i in ranked)
    # Summer pieces should dominate the kept tops; winter wool should be trimmed out.
    summer_tops = sum(1 for i in ranked if i["category"] == "tops" and "summer" in i.get("season", []))
    winter_tops = sum(1 for i in ranked if i["category"] == "tops" and "winter" in i.get("season", []))
    assert summer_tops > winter_tops
    assert "Linen Tee" in names


def test_ranking_preserves_category_coverage():
    closet = _big_closet()
    cold = {"avg_high": 4, "rainy_days": 2}
    ranked = ps._rank_closet_for_trip(closet, cold, [], "leisure", None, ps.BAG_CONSTRAINTS["medium_suitcase"])
    cats = {ps._normalise_category(i["category"]) for i in ranked}
    # Every outfit-critical category must survive the trim.
    assert {"tops", "bottoms", "shoes"}.issubset(cats)
    # The rain jacket (waterproof, all-season) should survive a rainy cold trip.
    assert any(i["name"] == "Rain Jacket" for i in ranked)


# ── Scored eval ────────────────────────────────────────────────────────────────


_SCENARIOS = [
    # (avg_high, season_of_appropriate_items, trimmed-must-keep category set)
    {"avg_high": 33, "rainy_days": 0, "want_season": "summer", "purpose": "beach"},
    {"avg_high": 2, "rainy_days": 3, "want_season": "winter", "purpose": "leisure"},
    {"avg_high": 30, "rainy_days": 0, "want_season": "summer", "purpose": "leisure"},
]


def test_weather_fit_score_meets_threshold():
    """
    Aggregate eval: across scenarios, what fraction of kept tops match the
    weather-appropriate season? Asserts a quality floor so heuristic
    regressions are caught.
    """
    closet = _big_closet()
    hits = 0
    total = 0
    for sc in _SCENARIOS:
        weather = {"avg_high": sc["avg_high"], "rainy_days": sc["rainy_days"]}
        ranked = ps._rank_closet_for_trip(closet, weather, [], sc["purpose"], None, ps.BAG_CONSTRAINTS["carry_on"])
        tops = [i for i in ranked if i["category"] == "tops"]
        for t in tops:
            total += 1
            if sc["want_season"] in t.get("season", []):
                hits += 1
    weather_fit = hits / total if total else 0.0
    assert weather_fit >= 0.75, f"weather-fit {weather_fit:.0%} below 75% threshold"


def test_grounding_rate_is_total():
    """
    Eval: with a mix of real and invented items, grounding must leave ZERO
    items presented as owned-but-nonexistent.
    """
    closet = [_item("a", "Real Tee", "tops"), _item("b", "Real Jeans", "bottoms")]
    valid_ids = {"a", "b"}
    day_plans = [
        {
            "outfits": [
                {
                    "items": [
                        {"closet_item_id": "a", "item_name": "Real Tee", "category": "tops", "source": "from_closet"},
                        {
                            "closet_item_id": "zzz",
                            "item_name": "Fake Blazer",
                            "category": "outerwear",
                            "source": "from_closet",
                        },
                        {
                            "closet_item_id": "",
                            "item_name": "Real Jeans",
                            "category": "bottoms",
                            "source": "from_closet",
                        },
                    ]
                }
            ]
        }
    ]
    grounded, _ = ps._ground_day_plans_to_closet(day_plans, closet)
    leaked = [
        it
        for it in grounded[0]["outfits"][0]["items"]
        if it["source"] == "from_closet" and str(it.get("closet_item_id")) not in valid_ids
    ]
    assert leaked == [], f"{len(leaked)} invented item(s) still presented as owned"
