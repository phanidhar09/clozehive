"""Unit tests for the weekly planner's pure logic.

Covers:
- infer_occasion (weekday vs weekend default)
- _needs_outerwear (cold / rainy detection)
- fallback_week_plan (deterministic rotation, dress handling, outerwear days)
- _validate_plan (AI output validation: id filtering, missing days backfilled)
"""

from __future__ import annotations

from datetime import date

from app.api.v1.wardrobe.services.weekly_planner_service import (
    _needs_outerwear,
    _validate_plan,
    fallback_week_plan,
    infer_occasion,
)


def _item(id_: str, category: str, wear_count: int = 0) -> dict:
    return {"id": id_, "name": f"item-{id_}", "category": category, "wear_count": wear_count}


def _day(d: str, condition: str = "Sunny", high: float = 24.0, low: float = 15.0) -> dict:
    return {"date": d, "condition": condition, "temp_high": high, "temp_low": low}


CLOSET = [
    _item("t1", "tops", 3),
    _item("t2", "tops", 0),
    _item("b1", "bottoms", 1),
    _item("b2", "bottoms", 5),
    _item("s1", "shoes", 2),
    _item("o1", "outerwear", 0),
    _item("d1", "dresses", 4),
]


# ── infer_occasion ────────────────────────────────────────────────────────────


class TestInferOccasion:
    def test_weekday_is_business_casual(self):
        assert infer_occasion(date(2026, 6, 11)) == "business casual"  # Thursday

    def test_weekend_is_casual(self):
        assert infer_occasion(date(2026, 6, 13)) == "casual"  # Saturday
        assert infer_occasion(date(2026, 6, 14)) == "casual"  # Sunday


# ── _needs_outerwear ──────────────────────────────────────────────────────────


class TestNeedsOuterwear:
    def test_cold_day(self):
        assert _needs_outerwear(_day("2026-06-12", "Sunny", high=10.0))

    def test_rainy_day(self):
        assert _needs_outerwear(_day("2026-06-12", "Light Rain", high=25.0))

    def test_warm_clear_day(self):
        assert not _needs_outerwear(_day("2026-06-12", "Sunny", high=25.0))

    def test_missing_temp_defaults_warm(self):
        assert not _needs_outerwear({"date": "2026-06-12", "condition": "Clear", "temp_high": None})


# ── fallback_week_plan ────────────────────────────────────────────────────────


class TestFallbackWeekPlan:
    def test_one_entry_per_day(self):
        days = [_day(f"2026-06-{8 + i:02d}") for i in range(7)]
        plan = fallback_week_plan(CLOSET, days)
        assert [p["date"] for p in plan] == [d["date"] for d in days]

    def test_least_worn_picked_first(self):
        plan = fallback_week_plan(CLOSET, [_day("2026-06-08")])
        # t2 has wear_count 0 → first top out of the rotation.
        assert "t2" in plan[0]["item_ids"]

    def test_no_repeats_until_pool_exhausted(self):
        days = [_day("2026-06-08"), _day("2026-06-09")]
        plan = fallback_week_plan(CLOSET, days)
        # Tops and bottoms have 2+ candidates → must not repeat across the two
        # days. Shoes only have one candidate, so s1 is allowed on both days.
        repeats = set(plan[0]["item_ids"]) & set(plan[1]["item_ids"])
        assert repeats == {"s1"}

    def test_dress_skips_bottom(self):
        closet = [_item("d1", "dresses"), _item("b1", "bottoms"), _item("s1", "shoes")]
        plan = fallback_week_plan(closet, [_day("2026-06-08")])
        assert plan[0]["item_ids"] == ["d1", "s1"]

    def test_outerwear_added_on_cold_day(self):
        plan = fallback_week_plan(CLOSET, [_day("2026-06-08", "Cloudy", high=8.0)])
        assert "o1" in plan[0]["item_ids"]

    def test_no_outerwear_on_warm_day(self):
        plan = fallback_week_plan(CLOSET, [_day("2026-06-08", "Sunny", high=28.0)])
        assert "o1" not in plan[0]["item_ids"]

    def test_empty_closet_yields_empty_outfits(self):
        plan = fallback_week_plan([], [_day("2026-06-08")])
        assert plan[0]["item_ids"] == []


# ── _validate_plan ────────────────────────────────────────────────────────────


class TestValidatePlan:
    DAYS = [_day("2026-06-08"), _day("2026-06-09")]

    def test_valid_plan_passes_through(self):
        data = {
            "days": [
                {"date": "2026-06-08", "occasion": "work", "item_ids": ["t1", "b1"], "reasoning": "ok"},
                {"date": "2026-06-09", "occasion": "casual", "item_ids": ["t2", "b2"], "reasoning": "ok"},
            ]
        }
        plan = _validate_plan(data, CLOSET, self.DAYS)
        assert plan is not None
        assert plan[0]["item_ids"] == ["t1", "b1"]
        assert plan[1]["source"] == "fani"

    def test_unknown_item_ids_filtered(self):
        data = {"days": [{"date": "2026-06-08", "item_ids": ["t1", "not-mine"], "reasoning": ""}]}
        plan = _validate_plan(data, CLOSET, [self.DAYS[0]])
        assert plan is not None
        assert plan[0]["item_ids"] == ["t1"]

    def test_missing_day_backfilled_from_fallback(self):
        data = {"days": [{"date": "2026-06-08", "item_ids": ["t1"], "reasoning": ""}]}
        plan = _validate_plan(data, CLOSET, self.DAYS)
        assert plan is not None
        assert len(plan) == 2
        assert plan[1]["source"] == "fallback"

    def test_missing_occasion_inferred(self):
        data = {"days": [{"date": "2026-06-13", "item_ids": ["t1"], "reasoning": ""}]}  # Saturday
        plan = _validate_plan(data, CLOSET, [_day("2026-06-13")])
        assert plan is not None
        assert plan[0]["occasion"] == "casual"

    def test_not_a_dict_rejected(self):
        assert _validate_plan(["nope"], CLOSET, self.DAYS) is None

    def test_all_days_invalid_rejected(self):
        data = {"days": [{"date": "2026-06-08", "item_ids": ["ghost"], "reasoning": ""}]}
        assert _validate_plan(data, CLOSET, self.DAYS) is None
