"""Unit tests for the static festival calendar (Phase 0, no external API)."""

from datetime import date

from app.api.v1.intelligence.services import festival_calendar as fc


# ── Country inference ─────────────────────────────────────────────────────────

def test_infer_country_from_country_name():
    assert fc.infer_country("Jaipur, India") == "india"
    assert fc.infer_country("United States") == "usa"


def test_infer_country_from_city_only():
    assert fc.infer_country("Mumbai") == "india"
    assert fc.infer_country("New York") == "usa"
    assert fc.infer_country("Dubai") == "uae"


def test_infer_country_unknown_returns_none():
    assert fc.infer_country("Narnia") is None
    assert fc.infer_country("") is None
    assert fc.infer_country(None) is None


# ── Date / country scoping ────────────────────────────────────────────────────

def test_country_scoped_festival_only_for_that_country():
    diwali = date(2026, 11, 8)
    assert [f["name"] for f in fc.festivals_on("india", diwali)] == ["Diwali"]
    # Diwali is not a US festival — must not leak.
    assert fc.festivals_on("usa", diwali) == []


def test_global_festival_applies_to_everyone():
    xmas = date(2026, 12, 25)
    assert [f["name"] for f in fc.festivals_on(None, xmas)] == ["Christmas"]
    assert [f["name"] for f in fc.festivals_on("japan", xmas)] == ["Christmas"]


def test_no_festival_on_ordinary_day():
    assert fc.festivals_on("india", date(2026, 6, 10)) == []


# ── Trip-range detection ──────────────────────────────────────────────────────

def test_festivals_in_range_finds_festival_during_trip():
    hits = fc.festivals_in_range("india", date(2026, 11, 5), date(2026, 11, 10))
    assert len(hits) == 1
    occ_date, fest = hits[0]
    assert occ_date == date(2026, 11, 8)
    assert fest["name"] == "Diwali"


def test_festival_outside_trip_window_excluded():
    # Trip ends the day before Diwali — must not be recommended.
    assert fc.festivals_in_range("india", date(2026, 11, 1), date(2026, 11, 7)) == []


# ── Lookahead ─────────────────────────────────────────────────────────────────

def test_next_festival_respects_lookahead_window():
    # Nothing within the default window of an ordinary June day.
    assert fc.next_festival("india", date(2026, 6, 10)) is None
    # Diwali is 3 days out from Nov 5 — inside the default window.
    nf = fc.next_festival("india", date(2026, 11, 5))
    assert nf is not None and nf[1]["name"] == "Diwali"


# ── Prompt helpers ────────────────────────────────────────────────────────────

def test_context_block_contains_dress_guidance():
    fest = fc.festivals_on("india", date(2026, 11, 8))[0]
    block = fc.build_festival_context_block(fest, when="today")
    assert "Diwali" in block
    assert "FESTIVAL CONTEXT" in block
    assert fc.festival_occasion(fest) in block
