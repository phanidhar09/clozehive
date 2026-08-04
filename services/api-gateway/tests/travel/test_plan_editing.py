"""
Tests for user editing of a generated packing plan.

Everything here is deterministic — plan editing never calls the LLM. The whole
feature rests on two guarantees:

1. Mutating ``day_plans_rich`` and re-deriving keeps every dependent section
   (checklist, bag capacity, closet-take list, rewear) in agreement with the
   plan the user is looking at.
2. User intent recorded in ``user_edits`` survives a regeneration — pinned days
   are spliced back verbatim and checklist deltas are replayed.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.api.v1.travel.services import packing_service as ps
from app.api.v1.travel.services.trips_service import TripsService
from app.models.packing import PackingPlan
from app.models.trips import Trip
from app.models.user import User

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _item(item_id: str, name: str, category: str, **extra: Any) -> dict[str, Any]:
    return {"id": item_id, "name": name, "category": category, **extra}


def _closet() -> list[dict[str, Any]]:
    return [
        _item("t1", "White Oxford Shirt", "tops", image_url="/t1.jpg", season=["all"]),
        _item("t2", "Navy Linen Tee", "tops", image_url="/t2.jpg", season=["summer"]),
        _item("t3", "Grey Merino Polo", "tops", season=["all"]),
        _item("t4", "Black Henley", "tops", season=["all"]),
        _item("b1", "Charcoal Chinos", "bottoms", image_url="/b1.jpg", season=["all"]),
        _item("b2", "Beige Shorts", "bottoms", season=["summer"]),
        _item("s1", "Brown Loafers", "shoes", image_url="/s1.jpg", season=["all"]),
        _item("s2", "White Sneakers", "shoes", season=["all"]),
        _item("o1", "Rain Jacket", "outerwear", season=["all"], tags=["waterproof"]),
    ]


def _outfit(slot: str, activity: str, item_ids: list[tuple[str, str, str]]) -> dict[str, Any]:
    return {
        "slot": slot,
        "activity": activity,
        "outfit_name": f"{activity} look",
        "items": [
            {"closet_item_id": cid, "item_name": name, "category": cat, "source": "from_closet"}
            for cid, name, cat in item_ids
        ],
        "styling_notes": "Tuck the shirt for a sharper line.",
        "comfort_notes": "",
        "rewear_notes": "",
    }


def _day_plans() -> list[dict[str, Any]]:
    return [
        {
            "day_number": 1,
            "date": "2026-08-01",
            "weather_note": "Mild",
            "activities": ["Sightseeing"],
            "outfits": [
                _outfit(
                    "morning",
                    "Sightseeing",
                    [
                        ("t1", "White Oxford Shirt", "tops"),
                        ("b1", "Charcoal Chinos", "bottoms"),
                        ("s1", "Brown Loafers", "shoes"),
                    ],
                )
            ],
        },
        {
            "day_number": 2,
            "date": "2026-08-02",
            "weather_note": "Warm",
            "activities": ["Beach"],
            "outfits": [
                _outfit(
                    "afternoon",
                    "Beach",
                    [
                        ("t2", "Navy Linen Tee", "tops"),
                        ("b2", "Beige Shorts", "bottoms"),
                        ("s1", "Brown Loafers", "shoes"),
                    ],
                )
            ],
        },
    ]


def _recompute(day_plans, **kwargs):
    defaults: dict[str, Any] = {
        "closet_items": _closet(),
        "missing_items": [],
        "rewear_strategy": [],
        "trip_days": 2,
        "bag_size": "carry_on",
        "user_edits": {},
    }
    defaults.update(kwargs)
    return ps.recompute_plan_sections(day_plans, **defaults)


# ── Re-derive keeps every dependent section in step ────────────────────────────


def test_recompute_builds_checklist_from_day_plans():
    derived = _recompute(_day_plans())
    names = {row["item_name"] for row in derived["packing_checklist"]}
    assert {"White Oxford Shirt", "Navy Linen Tee", "Charcoal Chinos", "Beige Shorts", "Brown Loafers"} <= names


def test_swapping_an_item_updates_checklist_and_take_list():
    plans = _day_plans()
    # Swap the Day 1 shirt for the merino polo.
    plans[0]["outfits"][0]["items"][0] = {
        "closet_item_id": "t3",
        "item_name": "Grey Merino Polo",
        "category": "tops",
        "source": "from_closet",
    }
    derived = _recompute(plans)

    names = {row["item_name"] for row in derived["packing_checklist"]}
    assert "Grey Merino Polo" in names
    assert "White Oxford Shirt" not in names

    take_ids = {row["item_id"] for row in derived["take_from_your_closet"]}
    assert "t3" in take_ids and "t1" not in take_ids


def test_recompute_reflects_edits_in_bag_capacity():
    plans = _day_plans()
    base = _recompute(plans, bag_size="backpack")["bag_capacity_summary"]
    assert base["items_per_category"]["tops"] == 2

    # Backpack allows 3 tops; add two more so the plan tips over the limit.
    plans[0]["outfits"][0]["items"].append(
        {"closet_item_id": "t3", "item_name": "Grey Merino Polo", "category": "tops", "source": "from_closet"}
    )
    plans[1]["outfits"][0]["items"].append(
        {"closet_item_id": "t4", "item_name": "Black Henley", "category": "tops", "source": "from_closet"}
    )
    after = _recompute(plans, bag_size="backpack")["bag_capacity_summary"]
    assert after["items_per_category"]["tops"] == 4
    assert after["packing_status"] == "overpacked"


def test_recompute_regrounds_an_edit_that_smuggles_in_a_foreign_id():
    """An id the user does not own must not survive an edit."""
    plans = _day_plans()
    plans[0]["outfits"][0]["items"][0] = {
        "closet_item_id": "not-mine",
        "item_name": "Someone Else's Jacket",
        "category": "outerwear",
        "source": "from_closet",
    }
    derived = _recompute(plans)
    edited = derived["day_plans_rich"][0]["outfits"][0]["items"][0]
    assert edited["closet_item_id"] is None
    assert edited["source"] == "missing_recommended"


def test_recompute_backfills_images_after_an_edit():
    plans = _day_plans()
    derived = _recompute(plans)
    first = derived["day_plans_rich"][0]["outfits"][0]["items"][0]
    assert first["image_url"] == "/t1.jpg"


# ── Checklist deltas ───────────────────────────────────────────────────────────


def test_user_added_item_appears_on_checklist():
    edits = {"checklist_added": [{"closet_item_id": "o1", "note": "just in case"}]}
    derived = _recompute(_day_plans(), user_edits=edits)
    added = [r for r in derived["packing_checklist"] if r["closet_item_id"] == "o1"]
    assert len(added) == 1
    assert added[0]["source"] == "user_added"
    assert added[0]["item_name"] == "Rain Jacket"


def test_user_added_item_already_planned_is_not_duplicated():
    edits = {"checklist_added": [{"closet_item_id": "t1"}]}
    derived = _recompute(_day_plans(), user_edits=edits)
    assert len([r for r in derived["packing_checklist"] if r["closet_item_id"] == "t1"]) == 1


def test_user_added_item_no_longer_owned_is_skipped():
    """An item deleted from the closet must not render as a phantom row."""
    edits = {"checklist_added": [{"closet_item_id": "deleted-item"}]}
    derived = _recompute(_day_plans(), user_edits=edits)
    assert all(r.get("closet_item_id") != "deleted-item" for r in derived["packing_checklist"])


def test_removed_checklist_row_disappears():
    edits = {"checklist_removed": ["t1"]}
    derived = _recompute(_day_plans(), user_edits=edits)
    assert all(r.get("closet_item_id") != "t1" for r in derived["packing_checklist"])


def test_essentials_can_be_removed_by_name_key():
    edits = {"checklist_removed": ["sleepwear"]}
    derived = _recompute(_day_plans(), user_edits=edits)
    assert all(r["item_name"].lower() != "sleepwear" for r in derived["packing_checklist"])


# ── Rewear strategy stays honest after an edit ─────────────────────────────────


def test_rewear_entry_survives_when_item_still_worn_twice():
    rewear = [{"item_name": "Brown Loafers", "closet_item_id": "s1", "worn_on_days": [], "reason": "Goes with all"}]
    derived = _recompute(_day_plans(), rewear_strategy=rewear)
    assert len(derived["rewear_strategy"]) == 1
    entry = derived["rewear_strategy"][0]
    assert entry["worn_on_days"] == ["Day 1", "Day 2"]
    assert entry["reason"] == "Goes with all"  # LLM prose carried through


def test_rewear_entry_dropped_when_edit_leaves_item_worn_once():
    plans = _day_plans()
    # Replace the Day 2 loafers with sneakers — loafers now worn only once.
    plans[1]["outfits"][0]["items"][2] = {
        "closet_item_id": "s2",
        "item_name": "White Sneakers",
        "category": "shoes",
        "source": "from_closet",
    }
    rewear = [{"item_name": "Brown Loafers", "closet_item_id": "s1", "worn_on_days": ["Day 1", "Day 2"], "reason": "x"}]
    derived = _recompute(plans, rewear_strategy=rewear)
    assert derived["rewear_strategy"] == []


# ── Closet-gap suggestions ─────────────────────────────────────────────────────


def test_suggestions_offer_owned_items_for_uncovered_roles():
    """The plan uses no outerwear; a carry-on allows one, so suggest the owned jacket."""
    suggestions = ps.suggest_closet_additions(
        _day_plans(),
        closet_items=_closet(),
        weather_summary={"avg_high": 18, "avg_low": 10, "rainy_days": 2},
        activities=[{"name": "Sightseeing"}],
        purpose="leisure",
        trip_style="casual",
        bag_size="carry_on",
    )
    outerwear = [s for s in suggestions if s["category"] == "outerwear"]
    assert outerwear and outerwear[0]["closet_item_id"] == "o1"


def test_suggestions_never_repeat_already_planned_items():
    suggestions = ps.suggest_closet_additions(
        _day_plans(),
        closet_items=_closet(),
        weather_summary={"avg_high": 22, "avg_low": 14, "rainy_days": 0},
        activities=[],
        purpose="leisure",
        trip_style=None,
        bag_size="large_suitcase",
    )
    planned = {"t1", "t2", "b1", "b2", "s1"}
    assert not ({s["closet_item_id"] for s in suggestions} & planned)


# ── Packed-state reconciliation ────────────────────────────────────────────────


def test_orphaned_packed_state_keys_are_dropped():
    checklist = [{"closet_item_id": "t1", "item_name": "White Oxford Shirt"}]
    state = {"t1": True, "gone-item": True}
    assert TripsService._reconcile_checklist_state(state, checklist) == {"t1": True}


def test_checklist_key_matches_the_frontend_convention():
    """The UI keys rows by closet_item_id, falling back to the lowercased name."""
    assert ps.checklist_key({"closet_item_id": "t1", "item_name": "White Oxford Shirt"}) == "t1"
    assert ps.checklist_key({"closet_item_id": None, "item_name": "Sleepwear"}) == "sleepwear"


# ── Pinning ────────────────────────────────────────────────────────────────────


def test_editing_a_day_pins_it():
    edits: dict[str, Any] = {}
    TripsService._pin_day(edits, 3)
    TripsService._pin_day(edits, 1)
    TripsService._pin_day(edits, 3)  # idempotent
    assert edits["pinned_days"] == [1, 3]


# ── Regeneration preserves pinned days ─────────────────────────────────────────


def _stub_generation(monkeypatch, ai_day_plans: list[dict[str, Any]]) -> dict[str, Any]:
    """Stub every external call in generate_packing_list; capture the AI kwargs."""
    captured: dict[str, Any] = {}

    async def _weather(*_a, **_k):
        return [{"date": "2026-08-01", "condition": "Sunny", "temp_high": 24, "temp_low": 16}]

    async def _location(*_a, **_k):
        return ""

    async def _fake_ai(*args, **kwargs):
        captured.update(kwargs)
        return {
            "trip_summary": {"style_direction": "s", "climate_summary": "c", "location_etiquette": "e"},
            "day_plans": ai_day_plans,
            "rewear_strategy": [],
            "missing_items": [],
            "bag_capacity_summary": {},
        }

    monkeypatch.setattr(ps, "fetch_weather_async", _weather)
    monkeypatch.setattr(ps, "build_location_context_block_async", _location)
    monkeypatch.setattr(ps, "_ai_activity_aware_packing", _fake_ai)
    monkeypatch.setattr(ps.festival_discovery, "get_trip_festivals", _location)
    monkeypatch.setattr(ps.festival_discovery, "build_trip_festival_block", lambda *_a, **_k: "")
    monkeypatch.setattr(ps.venue_rules_service, "get_venue_rules", _location)
    monkeypatch.setattr(ps.venue_rules_service, "build_venue_rules_block", lambda *_a, **_k: "")
    return captured


@pytest.mark.real_packing
async def test_regeneration_keeps_pinned_day_and_takes_ai_output_for_the_rest(monkeypatch):
    pinned = _day_plans()[0]  # user-finalised Day 1
    # The model is told to skip Day 1 and only returns Day 2.
    ai_day2 = {
        "day_number": 2,
        "date": "2026-08-02",
        "weather_note": "Warm",
        "activities": ["Dinner"],
        "outfits": [
            _outfit("evening", "Dinner", [("t3", "Grey Merino Polo", "tops"), ("b1", "Charcoal Chinos", "bottoms")])
        ],
    }
    captured = _stub_generation(monkeypatch, [ai_day2])

    result = await ps.generate_packing_list(
        "Lisbon",
        "2026-08-01",
        "2026-08-02",
        "leisure",
        _closet(),
        bag_size="carry_on",
        pinned_day_plans=[pinned],
    )

    days = result["day_plans_rich"]
    assert [d["day_number"] for d in days] == [1, 2]
    # Day 1 is the user's, untouched.
    day1_items = {i["closet_item_id"] for i in days[0]["outfits"][0]["items"]}
    assert day1_items == {"t1", "b1", "s1"}
    # Day 2 came from the model.
    assert days[1]["outfits"][0]["activity"] == "Dinner"
    # The pinned day was handed to the prompt so rewear/bag maths can see it.
    assert captured["pinned_day_plans"] == [pinned]


@pytest.mark.real_packing
async def test_pinned_day_wins_if_the_model_replans_it_anyway(monkeypatch):
    """The model is told to skip pinned days; if it disobeys, the user still wins."""
    pinned = _day_plans()[0]
    rogue_day1 = {
        "day_number": 1,
        "date": "2026-08-01",
        "weather_note": "",
        "activities": ["Sightseeing"],
        "outfits": [_outfit("morning", "Sightseeing", [("t2", "Navy Linen Tee", "tops")])],
    }
    _stub_generation(monkeypatch, [rogue_day1])

    result = await ps.generate_packing_list(
        "Lisbon", "2026-08-01", "2026-08-01", "leisure", _closet(), bag_size="carry_on", pinned_day_plans=[pinned]
    )

    days = result["day_plans_rich"]
    assert len(days) == 1
    assert {i["closet_item_id"] for i in days[0]["outfits"][0]["items"]} == {"t1", "b1", "s1"}


@pytest.mark.real_packing
async def test_checklist_deltas_replay_after_regeneration(monkeypatch):
    """A user-added item must still be on the checklist once the plan is rebuilt."""
    ai_day1 = _day_plans()[0]
    _stub_generation(monkeypatch, [ai_day1])

    result = await ps.generate_packing_list(
        "Lisbon",
        "2026-08-01",
        "2026-08-01",
        "leisure",
        _closet(),
        bag_size="carry_on",
        user_edits={"checklist_added": [{"closet_item_id": "o1"}], "checklist_removed": ["s1"]},
    )

    rows = {r.get("closet_item_id") for r in result["packing_checklist"]}
    assert "o1" in rows  # survived the rebuild
    assert "s1" not in rows  # removal survived too
