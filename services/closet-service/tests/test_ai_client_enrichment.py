"""Unit tests for ai_client response-enrichment shims — no HTTP."""

from __future__ import annotations

from app.services.ai_client import _enrich_agent_packing_for_trips


class TestEnrichAgentPackingForTrips:
    def test_maps_packing_list_to_take_from_closet(self) -> None:
        data = {
            "packing_list": [
                {"name": "Navy Chinos", "category": "bottoms", "available_in_closet": True,
                 "closet_item_id": "aaa", "reason": "Versatile."},
                {"name": "Rain Jacket", "category": "outerwear", "available_in_closet": False},
            ],
            "missing_items": [{"name": "Sunscreen", "category": "toiletries"}],
        }
        out = _enrich_agent_packing_for_trips(data)
        assert out["take_from_your_closet"] == [{
            "item_id": "aaa", "name": "Navy Chinos", "category": "bottoms",
            "reason": "Versatile.", "recommended_days": [],
        }]
        assert out["you_might_still_need"] == [{
            "name": "Sunscreen", "category": "toiletries", "reason": "Consider bringing this.",
        }]
        # items alias mirrors packing_list for legacy consumers
        assert out["items"] == data["packing_list"]

    def test_existing_keys_not_overwritten(self) -> None:
        data = {
            "take_from_your_closet": [{"name": "Already here"}],
            "you_might_still_need": [{"name": "Keep me"}],
            "packing_list": [{"name": "X", "available_in_closet": True}],
        }
        out = _enrich_agent_packing_for_trips(data)
        assert out["take_from_your_closet"] == [{"name": "Already here"}]
        assert out["you_might_still_need"] == [{"name": "Keep me"}]

    def test_non_dict_and_unavailable_entries_skipped(self) -> None:
        data = {"packing_list": ["garbage", {"name": "No flag"}], "missing_items": ["junk"]}
        out = _enrich_agent_packing_for_trips(data)
        assert out["take_from_your_closet"] == []
        assert out["you_might_still_need"] == []

    def test_defaults_fill_missing_fields(self) -> None:
        data = {"packing_list": [{"available_in_closet": True}]}
        out = _enrich_agent_packing_for_trips(data)
        entry = out["take_from_your_closet"][0]
        assert entry["item_id"] is None
        assert entry["category"] == "general"
        assert entry["reason"] == "Recommended for this trip."
