from types import SimpleNamespace

from app.services.analytics_service import AnalyticsService


def item(category: str, color: str = "black", occasion: list[str] | None = None):
    return SimpleNamespace(category=category, color=color, occasion=occasion or ["casual"])


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
