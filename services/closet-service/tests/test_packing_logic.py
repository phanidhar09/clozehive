"""Unit tests for packing_service pure helpers — no LLM, no network."""

from __future__ import annotations

import json

from app.services.packing_service import (
    BAG_CONSTRAINTS,
    _build_packing_checklist,
    _enrich_day_plans_with_images,
    _format_activities_for_prompt,
    _format_closet_for_prompt,
    _get_bag_constraints,
    _normalise_category,
    _normalise_packing_output,
    _per_day_weather_table,
)


class TestBagConstraints:
    def test_known_bag_size(self) -> None:
        assert _get_bag_constraints("backpack")["label"] == "Backpack only"
        assert _get_bag_constraints("backpack")["max_shoes"] == 1

    def test_none_falls_back_to_default(self) -> None:
        assert _get_bag_constraints(None) == BAG_CONSTRAINTS["none"]

    def test_unknown_bag_size_falls_back_to_default(self) -> None:
        assert _get_bag_constraints("steamer-trunk") == BAG_CONSTRAINTS["none"]


class TestNormaliseCategory:
    def test_alias_matches(self) -> None:
        assert _normalise_category("Slim Jeans") == "bottoms"
        assert _normalise_category("sneaker") == "shoes"
        assert _normalise_category("Hoodie") == "tops"
        assert _normalise_category("trench coat") == "outerwear"
        assert _normalise_category("jumpsuit") == "dresses"

    def test_canonical_passthrough(self) -> None:
        assert _normalise_category("tops") == "tops"

    def test_unknown_category_lowercased(self) -> None:
        assert _normalise_category("  Gadgets ") == "gadgets"


class TestFormatClosetForPrompt:
    def test_includes_only_truthy_fields(self) -> None:
        items = [{"id": "1", "name": "Tee", "category": "tops", "color": "navy", "brand": ""}]
        parsed = json.loads(_format_closet_for_prompt(items))
        assert parsed == [{"id": "1", "name": "Tee", "category": "tops", "color": "navy"}]

    def test_occasion_key_aliases(self) -> None:
        items = [{"id": "1", "name": "Tee", "category": "tops", "occasions": ["casual"]}]
        assert json.loads(_format_closet_for_prompt(items))[0]["occasions"] == ["casual"]
        items = [{"id": "1", "name": "Tee", "category": "tops", "occasion": ["work"]}]
        assert json.loads(_format_closet_for_prompt(items))[0]["occasions"] == ["work"]


class TestFormatActivitiesForPrompt:
    def test_empty_list_returns_guidance(self) -> None:
        assert "No specific activities" in _format_activities_for_prompt([])

    def test_full_entry_formatting(self) -> None:
        out = _format_activities_for_prompt([
            {"name": "Client dinner", "day_number": 2, "time_of_day": "late_evening",
             "formality": "smart_casual", "is_fixed": True},
        ])
        assert "Client dinner" in out
        assert "Day 2" in out
        assert "late evening" in out
        assert "smart casual" in out
        assert "BOOKED" in out


class TestPerDayWeatherTable:
    def test_empty_returns_empty_string(self) -> None:
        assert _per_day_weather_table([]) == ""

    def test_caps_at_fourteen_days(self) -> None:
        days = [{"date": f"2026-07-{d:02d}", "condition": "sunny", "temp_high": 30, "temp_low": 20}
                for d in range(1, 21)]
        out = _per_day_weather_table(days)
        assert "Day 14" in out
        assert "Day 15" not in out


class TestNormalisePackingOutput:
    CLOSET = [
        {"id": "aaa", "name": "Navy Chinos"},
        {"id": "bbb", "name": "White Sneakers"},
    ]

    def test_real_items_kept_hallucinated_moved_to_still_need(self) -> None:
        ai_data = {
            "take_from_your_closet": [
                {"item_id": "aaa", "name": "Navy Chinos", "category": "Bottoms"},
                {"item_id": "zzz", "name": "Leather Jacket", "category": "outerwear"},
            ],
            "you_might_still_need": [{"name": "Sunscreen", "category": "toiletries"}],
        }
        take, need = _normalise_packing_output(ai_data, self.CLOSET)
        assert [t["name"] for t in take] == ["Navy Chinos"]
        assert take[0]["category"] == "bottoms"
        # Hallucinated closet item lands in still_need after real suggestions
        assert [n["name"] for n in need] == ["Sunscreen", "Leather Jacket"]

    def test_match_by_name_when_id_missing(self) -> None:
        ai_data = {"take_from_your_closet": [{"name": "white sneakers"}]}
        take, _ = _normalise_packing_output(ai_data, self.CLOSET)
        assert len(take) == 1

    def test_alias_keys_and_dedup(self) -> None:
        ai_data = {
            "takeFromCloset": [
                {"item_id": "aaa", "name": "Navy Chinos"},
                {"item_id": "aaa", "name": "navy chinos"},
            ],
            "shopping_list": [{"name": "Belt"}, {"name": "belt"}],
        }
        take, need = _normalise_packing_output(ai_data, self.CLOSET)
        assert len(take) == 1
        assert len(need) == 1


class TestEnrichDayPlansWithImages:
    def test_injects_image_url_for_matching_ids(self) -> None:
        closet = [{"id": "aaa", "image_url": "https://img/x.png"}]
        plans = [{"outfits": [{"items": [{"closet_item_id": "aaa"}, {"closet_item_id": "zzz"}]}]}]
        enriched = _enrich_day_plans_with_images(plans, closet)
        items = enriched[0]["outfits"][0]["items"]
        assert items[0]["image_url"] == "https://img/x.png"
        assert "image_url" not in items[1]


class TestBuildPackingChecklist:
    def test_rewear_counted_across_days_and_essentials_added(self) -> None:
        day_plans = [
            {"day_number": 1, "outfits": [{"activity": "Museum", "items": [
                {"closet_item_id": "aaa", "item_name": "Navy Chinos", "category": "chinos"}]}]},
            {"day_number": 2, "outfits": [{"activity": "Dinner", "items": [
                {"closet_item_id": "aaa", "item_name": "Navy Chinos", "category": "chinos"}]}]},
        ]
        checklist = _build_packing_checklist(day_plans, missing_items=[], trip_days=3)
        by_name = {e["item_name"]: e for e in checklist}
        chinos = by_name["Navy Chinos"]
        assert chinos["rewear_count"] == 2
        assert chinos["planned_days"] == ["Day 1", "Day 2"]
        assert chinos["activities"] == ["Museum", "Dinner"]
        assert chinos["category"] == "bottoms"
        # Essentials: underwear/socks scale with trip length
        assert by_name["Underwear"]["quantity"] == 3
        assert by_name["Socks"]["quantity"] == 3
        assert by_name["Phone charger"]["quantity"] == 1

    def test_missing_items_labelled_separately(self) -> None:
        checklist = _build_packing_checklist(
            [], missing_items=[{"name": "Rain Jacket", "category": "jacket", "priority": "high"}],
            trip_days=2,
        )
        rain = next(e for e in checklist if e["item_name"] == "Rain Jacket")
        assert rain["source"] == "missing_recommended"
        assert rain["priority"] == "high"
        assert rain["closet_item_id"] is None
