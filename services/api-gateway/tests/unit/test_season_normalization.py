"""Unit tests for season/occasions normalisation helpers.

Covers:
- _coerce_str_list  (schema helper — used by ClosetItemCreate/Response)
- _coerce_str_list_optional (schema helper — used by ClosetItemUpdate)
- _norm_list (fashion_analysis_service — AI output normalisation)
- _pick_season (vision_pipeline route — save-analyzed-items path)
- ClosetItemCreate / ClosetItemUpdate schema validators end-to-end
"""

from __future__ import annotations

import pytest

from app.schemas.closet import (
    ClosetItemCreate,
    ClosetItemResponse,
    ClosetItemUpdate,
    _coerce_str_list,
    _coerce_str_list_optional,
)
from app.services.fashion_analysis_service import _norm_list
from app.api.v1.vision_pipeline import _pick_season


# ── _coerce_str_list ──────────────────────────────────────────────────────────

class TestCoerceStrList:
    def test_none_returns_empty(self):
        assert _coerce_str_list(None) == []

    def test_empty_string_returns_empty(self):
        assert _coerce_str_list("") == []
        assert _coerce_str_list("   ") == []

    def test_single_string(self):
        assert _coerce_str_list("summer") == ["summer"]

    def test_single_string_uppercase_normalised(self):
        assert _coerce_str_list("Summer") == ["summer"]

    def test_comma_separated_string(self):
        assert _coerce_str_list("summer, spring") == ["summer", "spring"]

    def test_comma_separated_no_space(self):
        assert _coerce_str_list("summer,spring") == ["summer", "spring"]

    def test_list_passthrough(self):
        assert _coerce_str_list(["summer", "spring"]) == ["summer", "spring"]

    def test_list_deduplicates(self):
        assert _coerce_str_list(["summer", "summer", "spring"]) == ["summer", "spring"]

    def test_list_normalises_case(self):
        assert _coerce_str_list(["Summer", "SPRING"]) == ["summer", "spring"]

    def test_list_removes_blank_entries(self):
        assert _coerce_str_list(["summer", "", "  ", "fall"]) == ["summer", "fall"]

    def test_preserves_order(self):
        assert _coerce_str_list("fall, spring, summer") == ["fall", "spring", "summer"]


# ── _coerce_str_list_optional ─────────────────────────────────────────────────

class TestCoerceStrListOptional:
    def test_none_stays_none(self):
        assert _coerce_str_list_optional(None) is None

    def test_empty_string_returns_none(self):
        assert _coerce_str_list_optional("") is None
        assert _coerce_str_list_optional("   ") is None

    def test_single_string(self):
        assert _coerce_str_list_optional("summer") == ["summer"]

    def test_empty_list_returns_empty_list(self):
        # Explicit [] means "clear the field"
        assert _coerce_str_list_optional([]) == []

    def test_comma_separated(self):
        assert _coerce_str_list_optional("summer, fall") == ["summer", "fall"]


# ── _norm_list (fashion_analysis_service) ─────────────────────────────────────

class TestNormList:
    def test_none_returns_empty(self):
        assert _norm_list(None) == []

    def test_integer_returns_empty(self):
        assert _norm_list(42) == []

    def test_list_passthrough(self):
        assert _norm_list(["casual", "formal"]) == ["casual", "formal"]

    def test_list_strips_whitespace(self):
        assert _norm_list(["  casual  ", "formal"]) == ["casual", "formal"]

    def test_list_lowercases(self):
        assert _norm_list(["Casual", "FORMAL"]) == ["casual", "formal"]

    def test_list_deduplicates(self):
        assert _norm_list(["casual", "casual", "travel"]) == ["casual", "travel"]

    def test_comma_string(self):
        assert _norm_list("casual, travel") == ["casual", "travel"]

    def test_comma_string_no_space(self):
        assert _norm_list("casual,travel") == ["casual", "travel"]

    def test_single_string(self):
        assert _norm_list("summer") == ["summer"]

    def test_list_removes_empty_strings(self):
        assert _norm_list(["casual", "", "  "]) == ["casual"]

    def test_comma_string_deduplicates(self):
        assert _norm_list("summer, summer, fall") == ["summer", "fall"]


# ── _pick_season (vision_pipeline) ────────────────────────────────────────────

class TestPickSeason:
    def test_none_returns_empty(self):
        assert _pick_season(None) == []

    def test_empty_list_returns_empty(self):
        assert _pick_season([]) == []

    def test_single_valid_season(self):
        assert _pick_season(["summer"]) == ["summer"]

    def test_multiple_valid_seasons(self):
        assert _pick_season(["spring", "summer"]) == ["spring", "summer"]

    def test_autumn_mapped_to_fall(self):
        assert _pick_season(["autumn"]) == ["fall"]

    def test_invalid_value_dropped(self):
        assert _pick_season(["monsoon", "summer"]) == ["summer"]

    def test_deduplicates(self):
        assert _pick_season(["summer", "summer"]) == ["summer"]

    def test_case_insensitive(self):
        assert _pick_season(["Summer", "FALL"]) == ["summer", "fall"]

    def test_mixed_valid_invalid(self):
        result = _pick_season(["summer", "rainy", "winter", "autumn"])
        assert result == ["summer", "winter", "fall"]


# ── ClosetItemCreate schema end-to-end ────────────────────────────────────────

class TestClosetItemCreateSeason:
    _BASE = {"name": "Test Shirt", "category": "tops"}

    def test_no_season_defaults_to_empty_list(self):
        item = ClosetItemCreate(**self._BASE)
        assert item.season == []

    def test_single_string_season(self):
        item = ClosetItemCreate(**self._BASE, season="summer")
        assert item.season == ["summer"]

    def test_comma_separated_season(self):
        item = ClosetItemCreate(**self._BASE, season="summer, spring")
        assert item.season == ["summer", "spring"]

    def test_list_season(self):
        item = ClosetItemCreate(**self._BASE, season=["summer", "fall"])
        assert item.season == ["summer", "fall"]

    def test_none_season_becomes_empty(self):
        item = ClosetItemCreate(**self._BASE, season=None)
        assert item.season == []

    def test_season_lowercased(self):
        item = ClosetItemCreate(**self._BASE, season="Summer")
        assert item.season == ["summer"]

    def test_season_deduplicates(self):
        item = ClosetItemCreate(**self._BASE, season=["summer", "summer"])
        assert item.season == ["summer"]


# ── ClosetItemUpdate schema end-to-end ───────────────────────────────────────

class TestClosetItemUpdateSeason:
    def test_no_season_stays_none(self):
        update = ClosetItemUpdate()
        assert update.season is None

    def test_none_season_stays_none(self):
        update = ClosetItemUpdate(season=None)
        assert update.season is None

    def test_empty_string_becomes_none(self):
        update = ClosetItemUpdate(season="")
        assert update.season is None

    def test_single_string(self):
        update = ClosetItemUpdate(season="winter")
        assert update.season == ["winter"]

    def test_comma_separated(self):
        update = ClosetItemUpdate(season="winter, spring")
        assert update.season == ["winter", "spring"]

    def test_empty_list_preserved(self):
        # Explicitly sending [] means "clear seasons"
        update = ClosetItemUpdate(season=[])
        assert update.season == []

    def test_list_with_values(self):
        update = ClosetItemUpdate(season=["winter", "fall"])
        assert update.season == ["winter", "fall"]

    def test_season_excluded_from_dump_when_none(self):
        update = ClosetItemUpdate(season=None)
        dumped = update.model_dump(exclude_none=True)
        assert "season" not in dumped

    def test_empty_list_included_in_dump(self):
        update = ClosetItemUpdate(season=[])
        dumped = update.model_dump(exclude_none=True)
        assert dumped["season"] == []


# ── ClosetItemResponse coercion ───────────────────────────────────────────────

class TestClosetItemResponseSeason:
    """Verify the response schema coerces DB None → [] for old rows."""

    _BASE_ATTRS = {
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "00000000-0000-0000-0000-000000000002",
        "name": "T-Shirt",
        "category": "tops",
        "color": None,
        "fabric": None,
        "pattern": None,
        "occasion": None,
        "eco_score": None,
        "tags": None,
        "image_url": None,
        "notes": None,
        "brand": None,
        "size": None,
        "price": None,
        "wear_count": 0,
        "last_worn": None,
        "is_archived": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }

    def test_null_season_becomes_empty_list(self):
        resp = ClosetItemResponse(**self._BASE_ATTRS, season=None)
        assert resp.season == []

    def test_array_season_preserved(self):
        resp = ClosetItemResponse(**self._BASE_ATTRS, season=["summer", "spring"])
        assert resp.season == ["summer", "spring"]

    def test_string_season_coerced_to_list(self):
        # Guard against legacy rows that somehow stored a string
        resp = ClosetItemResponse(**self._BASE_ATTRS, season="summer")
        assert resp.season == ["summer"]
