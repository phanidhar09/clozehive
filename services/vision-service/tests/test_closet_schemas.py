"""Tests for closet schema helpers (category coercion + list coercion)."""

from __future__ import annotations

from app.schemas.closet import _coerce_str_list, coerce_closet_category


class TestCoerceClosetCategory:
    def test_canonical_passthrough(self):
        assert coerce_closet_category("tops") == "tops"
        assert coerce_closet_category("accessories") == "accessories"

    def test_case_and_whitespace_insensitive(self):
        assert coerce_closet_category("  TOPS ") == "tops"
        assert coerce_closet_category("Jeans") == "bottoms"

    def test_common_aliases(self):
        assert coerce_closet_category("t-shirt") == "tops"
        assert coerce_closet_category("sneakers") == "shoes"
        assert coerce_closet_category("blazer") == "outerwear"
        assert coerce_closet_category("jumpsuit") == "dresses"
        assert coerce_closet_category("watch") == "accessories"

    def test_unknown_and_empty_fall_back_to_other(self):
        assert coerce_closet_category("spaceship") == "other"
        assert coerce_closet_category("") == "other"
        assert coerce_closet_category(None) == "other"
        assert coerce_closet_category("   ") == "other"

    def test_uncategorised_spellings(self):
        assert coerce_closet_category("uncategorised") == "other"
        assert coerce_closet_category("uncategorized") == "other"


class TestCoerceStrList:
    def test_none_and_unknown_types(self):
        assert _coerce_str_list(None) == []
        assert _coerce_str_list(42) == []
        assert _coerce_str_list({"a": 1}) == []

    def test_comma_string_split_lowercased(self):
        assert _coerce_str_list("Summer, WINTER") == ["summer", "winter"]

    def test_list_input_drops_empties(self):
        assert _coerce_str_list(["Fall", "", None, " spring "]) == ["fall", "spring"]

    def test_dedupes_preserving_order(self):
        assert _coerce_str_list("summer, Summer, winter") == ["summer", "winter"]
