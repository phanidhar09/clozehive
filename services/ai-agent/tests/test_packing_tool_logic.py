"""Unit tests for the packing tool's pure planning helpers — no LLM, no network."""

from __future__ import annotations

from app.tools.packing import (
    _build_alerts,
    _build_daily_plan,
    _match_closet,
    _normalise_category,
    _normalise_purpose,
    _required_categories,
    _weather_extras,
)
from app.tools.schemas import ClosetItem, PackingItem, WeatherDay, WeatherSummary


def _summary(**kwargs) -> WeatherSummary:
    defaults = {
        "dominant_condition": "Sunny", "avg_high": 22.0, "avg_low": 14.0,
        "rainy_days": 0, "total_days": 4, "recommendation": "",
    }
    defaults.update(kwargs)
    return WeatherSummary(**defaults)


def _closet_item(name: str, category: str) -> ClosetItem:
    return ClosetItem(id=f"id-{name.lower().replace(' ', '-')}", name=name, category=category)


class TestNormalisers:
    def test_category_aliases(self) -> None:
        assert _normalise_category("Slim Jeans") == "bottoms"
        assert _normalise_category("Hoodie") == "tops"

    def test_unknown_purpose_falls_back(self) -> None:
        assert _normalise_purpose("") != ""
        assert _normalise_purpose("space-tourism") == _normalise_purpose("")

    def test_known_purpose_kept(self) -> None:
        assert _normalise_purpose("  Business ") == "business"


class TestRequiredCategories:
    def test_cold_weather_adds_outerwear(self) -> None:
        cats = _required_categories("beach", _summary(avg_high=5.0))
        assert "outerwear" in cats

    def test_cold_condition_adds_outerwear(self) -> None:
        cats = _required_categories("beach", _summary(dominant_condition="Snowy"))
        assert "outerwear" in cats

    def test_warm_weather_no_forced_outerwear(self) -> None:
        cats = _required_categories("beach", _summary(avg_high=30.0))
        assert "outerwear" not in cats


class TestMatchCloset:
    def test_available_categories_matched_with_ids(self) -> None:
        closet = [_closet_item("Navy Tee", "t-shirt"), _closet_item("Chinos", "pants")]
        matched, missing = _match_closet(closet, ["tops", "bottoms", "shoes"], trip_days=4)
        assert {m.category for m in matched} == {"tops", "bottoms"}
        assert all(m.available_in_closet and m.closet_item_id for m in matched)
        assert [m.category for m in missing] == ["shoes"]
        assert missing[0].available_in_closet is False

    def test_quantity_scales_with_trip_length_capped_at_four(self) -> None:
        closet = [_closet_item(f"Tee {i}", "t-shirt") for i in range(10)]
        matched, _ = _match_closet(closet, ["tops"], trip_days=20)
        assert len(matched) == 4
        matched, _ = _match_closet(closet, ["tops"], trip_days=1)
        assert len(matched) == 1


class TestWeatherExtras:
    def test_rainy_days_trigger_rain_gear(self) -> None:
        names = [e.name for e in _weather_extras(_summary(rainy_days=2), "business")]
        assert any("umbrella" in n.lower() or "rain" in n.lower() for n in names)

    def test_heat_triggers_sun_gear(self) -> None:
        names = [e.name for e in _weather_extras(_summary(avg_high=30.0), "business")]
        assert any("sunscreen" in n.lower() for n in names)

    def test_beach_purpose_adds_swimwear(self) -> None:
        names = [e.name for e in _weather_extras(_summary(), "beach")]
        assert "Swimwear" in names

    def test_mild_business_trip_no_extras(self) -> None:
        extras = _weather_extras(_summary(dominant_condition="Mild", avg_high=20.0), "business")
        assert extras == []


class TestBuildDailyPlan:
    def test_rotates_items_across_days(self) -> None:
        matched = [
            PackingItem(name="Tee A", category="tops"),
            PackingItem(name="Tee B", category="tops"),
            PackingItem(name="Chinos", category="bottoms"),
        ]
        days = [
            WeatherDay(date=f"2026-07-0{d}", condition="Sunny", temp_high=25, temp_low=15, description="")
            for d in range(1, 4)
        ]
        plans = _build_daily_plan(matched, _summary(days=days), "2026-07-01", "2026-07-03")
        assert len(plans) == 3
        assert plans[0].items == ["Tee A", "Chinos"]
        assert plans[1].items == ["Tee B", "Chinos"]
        assert plans[2].items == ["Tee A", "Chinos"]

    def test_days_without_forecast_skipped(self) -> None:
        days = [WeatherDay(date="2026-07-01", condition="Sunny", temp_high=25, temp_low=15, description="")]
        plans = _build_daily_plan([], _summary(days=days), "2026-07-01", "2026-07-05")
        assert len(plans) == 1


class TestBuildAlerts:
    def test_missing_categories_alert(self) -> None:
        alerts = _build_alerts(
            [PackingItem(name="Shoes (not in wardrobe)", category="shoes")],
            _summary(), trip_days=4,
        )
        assert any("shoes" in a for a in alerts)

    def test_rain_heat_and_cold_alerts(self) -> None:
        alerts = _build_alerts([], _summary(rainy_days=3, avg_high=36.0, avg_low=-2.0), trip_days=4)
        joined = " ".join(alerts)
        assert "rain" in joined
        assert "heat" in joined.lower()
        assert "thermal" in joined.lower()

    def test_no_alerts_for_mild_trip(self) -> None:
        assert _build_alerts([], _summary(), trip_days=4) == []
