import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.api.v1.platform.services.analytics_service import AnalyticsService


def item(category: str, color: str = "black", occasion: list[str] | None = None):
    return SimpleNamespace(category=category, color=color, occasion=occasion or ["casual"])


def value_item(
    *,
    name: str = "Item",
    category: str = "tops",
    price: float | None = None,
    wear_count: int = 0,
    last_worn: date | None = None,
    is_archived: bool = False,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        category=category,
        price=price,
        wear_count=wear_count,
        last_worn=last_worn,
        is_archived=is_archived,
    )


class _NoOutfitsSession:
    """Stub session whose outfit query returns no rows (versatility = empty)."""

    async def execute(self, *_args, **_kwargs):
        return SimpleNamespace(all=lambda: [])


def test_category_coverage_good_status():
    service = AnalyticsService(session=None)
    coverage = service._compute_category_coverage([item("tops") for _ in range(6)])
    tops = next(c for c in coverage if c.category == "tops")
    assert tops.status == "good"


def test_category_coverage_low_status():
    service = AnalyticsService(session=None)
    coverage = service._compute_category_coverage([item("tops")])
    tops = next(c for c in coverage if c.category == "tops")
    assert tops.status == "low"


def test_category_coverage_missing_status():
    service = AnalyticsService(session=None)
    coverage = service._compute_category_coverage([item("tops")])
    bottoms = next(c for c in coverage if c.category == "bottoms")
    assert bottoms.status == "missing"


def test_color_percentage_sums_to_100():
    service = AnalyticsService(session=None)
    items = [item("tops", "black") for _ in range(5)]
    items += [item("tops", "white") for _ in range(3)]
    items += [item("tops", "blue") for _ in range(2)]

    stats = service._compute_color_stats(items)
    percentages = {s.color: s.percentage for s in stats}

    assert percentages == {"black": 50.0, "white": 30.0, "blue": 20.0}
    assert sum(percentages.values()) == 100.0


def test_summary_strongest_category():
    service = AnalyticsService(session=None)
    items = [item("tops") for _ in range(8)]
    items += [item("bottoms") for _ in range(3)]
    items += [item("shoes")]

    summary = service._compute_summary(items)

    assert summary.strongest_category == "tops"


def test_outfit_readiness_estimated_outfits():
    service = AnalyticsService(session=None)
    ready_items = [item("tops"), item("bottoms"), item("shoes")]

    assert service._compute_outfit_readiness(ready_items).estimated_outfits > 0
    assert service._compute_outfit_readiness([]).estimated_outfits == 0


# ── Value & usage insights ──────────────────────────────────────────────────


async def _value(items):
    service = AnalyticsService(session=_NoOutfitsSession())
    return await service._compute_value_insights(uuid.uuid4(), items)


@pytest.mark.asyncio
async def test_cost_per_wear_and_value_split():
    items = [
        value_item(name="Boots", price=120.0, wear_count=20),  # $6/wear
        value_item(name="Blazer", price=200.0, wear_count=2),  # $100/wear
        value_item(name="Tag-on jeans", price=80.0, wear_count=0),  # unworn → no CPW
    ]
    v = await _value(items)

    assert v.items_priced == 3
    assert v.total_value == 400.0
    assert v.value_worn == 320.0  # boots + blazer
    assert v.value_unworn == 80.0  # the unworn jeans
    # Cost-per-wear ranks cheapest-first, and never-worn items are excluded.
    assert [round(c.cost_per_wear, 1) for c in v.best_value_items] == [6.0, 100.0]
    assert v.worst_value_items[0].name == "Blazer"


@pytest.mark.asyncio
async def test_utilization_rate_excludes_archived():
    items = [
        value_item(wear_count=1),  # worn
        value_item(wear_count=0),  # never worn
        value_item(wear_count=5, is_archived=True),  # archived → ignored entirely
    ]
    v = await _value(items)

    # 1 of 2 non-archived items has been worn.
    assert v.utilization_rate == 50.0


@pytest.mark.asyncio
async def test_forgotten_gems_flags_never_and_long_unworn():
    today = date.today()
    items = [
        value_item(name="Worn yesterday", wear_count=3, last_worn=today - timedelta(days=1)),
        value_item(name="Never worn", wear_count=0),
        value_item(name="Stale", wear_count=2, last_worn=today - timedelta(days=120)),
    ]
    v = await _value(items)

    names = {g.name for g in v.forgotten_gems}
    assert names == {"Never worn", "Stale"}
    assert "Worn yesterday" not in names


@pytest.mark.asyncio
async def test_value_insights_empty_when_no_items():
    v = await _value([])
    assert v.items_priced == 0
    assert v.utilization_rate == 0.0
    assert v.avg_cost_per_wear is None


# ── Weekly digest headline ──────────────────────────────────────────────────


def _digest_item(name="Item"):
    return SimpleNamespace(item_id="x", name=name, category="tops", detail="")


def test_headline_no_wears_but_new_items():
    h = AnalyticsService._digest_headline(
        wears_logged=0, items_worn=0, most_worn=None, new_items=2, forgotten_gem=None
    )
    assert "2 new pieces" in h


def test_headline_quiet_week():
    h = AnalyticsService._digest_headline(
        wears_logged=0, items_worn=0, most_worn=None, new_items=0, forgotten_gem=None
    )
    assert "Quiet week" in h


def test_headline_leads_with_most_worn():
    h = AnalyticsService._digest_headline(
        wears_logged=5,
        items_worn=3,
        most_worn=_digest_item("Linen shirt"),
        new_items=0,
        forgotten_gem=None,
    )
    assert "5 wears across 3 pieces" in h
    assert "Linen shirt" in h


def test_headline_singular_grammar():
    h = AnalyticsService._digest_headline(
        wears_logged=1, items_worn=1, most_worn=None, new_items=0, forgotten_gem=None
    )
    assert "1 wear across 1 piece" in h
