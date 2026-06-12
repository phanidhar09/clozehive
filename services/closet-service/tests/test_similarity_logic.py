"""Unit tests for closet_similarity_service pure scoring helpers — no DB, no embeddings."""

from __future__ import annotations

from app.models.closet import ClosetItem
from app.services.closet_similarity_service import (
    _build_difference_summary,
    _build_similarity_reason,
    _categories_compatible,
    _colors_are_close,
    _metadata_similarity_score,
    _similarity_label,
    _to_list,
)


class TestSimilarityLabel:
    def test_thresholds(self) -> None:
        assert _similarity_label(95) == "Possible duplicate"
        assert _similarity_label(90) == "Possible duplicate"
        assert _similarity_label(89) == "Very similar"
        assert _similarity_label(75) == "Very similar"
        assert _similarity_label(74) == "Related item"
        assert _similarity_label(55) == "Related item"
        assert _similarity_label(54) == "Not similar"
        assert _similarity_label(0) == "Not similar"


class TestColorsAreClose:
    def test_shared_word(self) -> None:
        assert _colors_are_close("navy blue", "sky blue") is True

    def test_neutrals_group(self) -> None:
        assert _colors_are_close("off-white", "cream") is True
        assert _colors_are_close("black", "ivory") is True

    def test_unrelated_colors(self) -> None:
        assert _colors_are_close("red", "green") is False


class TestToList:
    def test_list_normalised(self) -> None:
        assert _to_list(["Casual", " WORK "]) == ["casual", "work"]

    def test_string_wrapped(self) -> None:
        assert _to_list("Formal") == ["formal"]

    def test_none_and_empty(self) -> None:
        assert _to_list(None) == []
        assert _to_list("   ") == []


class TestCategoriesCompatible:
    def test_same_group(self) -> None:
        assert _categories_compatible("shirt", "tops") is True
        assert _categories_compatible("jeans", "shorts") is True

    def test_cross_group(self) -> None:
        assert _categories_compatible("shirt", "jeans") is False


def _item(**kwargs) -> ClosetItem:
    defaults: dict = {"name": "Existing", "category": "tops"}
    defaults.update(kwargs)
    return ClosetItem(**defaults)


class TestMetadataSimilarityScore:
    def test_full_match_caps_at_100(self) -> None:
        source = {
            "category": "tops", "color": "navy blue",
            "occasion_tags": ["casual", "work"], "season_tags": ["summer", "spring"],
            "pattern": "solid", "material": "cotton", "style_tags": ["minimal", "classic"],
        }
        item = _item(
            category="tops", color="navy blue", occasion=["casual", "work"],
            season=["summer", "spring"], pattern="solid", fabric="cotton",
            tags=["minimal", "classic"],
        )
        assert _metadata_similarity_score(source, item) == 100

    def test_no_overlap_scores_zero(self) -> None:
        source = {"category": "shoes", "color": "red"}
        item = _item(category="tops", color="green")
        assert _metadata_similarity_score(source, item) == 0

    def test_compatible_category_scores_half(self) -> None:
        source = {"category": "shirt"}
        item = _item(category="tops")
        assert _metadata_similarity_score(source, item) == 20

    def test_close_color_scores_half(self) -> None:
        source = {"category": "tops", "color": "navy blue"}
        item = _item(category="tops", color="sky blue")
        assert _metadata_similarity_score(source, item) == 40 + 10

    def test_missing_fields_are_neutral(self) -> None:
        source = {"category": "tops"}
        item = _item(category="tops")
        assert _metadata_similarity_score(source, item) == 40


class TestHumanReadableText:
    def test_difference_summary_mentions_color_and_material(self) -> None:
        out = _build_difference_summary(
            {"color": "Navy", "material": "cotton"},
            {"color": "olive", "fabric": "wool"},
        )
        assert "navy" in out and "olive" in out
        assert "cotton vs wool" in out

    def test_difference_summary_when_no_diffs(self) -> None:
        out = _build_difference_summary({"color": "navy"}, {"color": "navy"})
        assert "very similar" in out

    def test_similarity_reason_lists_shared_signals(self) -> None:
        out = _build_similarity_reason(
            80,
            {"category": "tops", "color": "navy", "occasion_tags": ["work"]},
            {"category": "tops", "color": "navy", "occasion": ["work", "casual"]},
        )
        assert "Same category (tops)" in out
        assert "Identical color (navy)" in out
        assert "work" in out
