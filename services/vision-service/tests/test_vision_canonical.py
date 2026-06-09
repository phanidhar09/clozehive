"""Tests for canonical vision payload normalization (schemas/vision_canonical.py).

This is the seam between messy LLM JSON and everything downstream — the
highest-value pure logic in the service.
"""

from __future__ import annotations

from app.schemas.vision_canonical import (
    NormalizedVisionAIOutput,
    normalize_confidence_value,
    normalize_vision_ai_dict,
    normalized_to_bulk_api_dict,
    normalized_to_legacy_upload_dict,
    parse_vision_ai_payload,
)


# ── normalize_confidence_value ────────────────────────────────────────────────

class TestNormalizeConfidence:
    def test_none_is_zero(self):
        assert normalize_confidence_value(None) == 0.0

    def test_fraction_passthrough(self):
        assert normalize_confidence_value(0.85) == 0.85

    def test_percentage_scaled_down(self):
        assert normalize_confidence_value(85) == 0.85
        assert normalize_confidence_value(100) == 1.0

    def test_above_100_clamped_to_one(self):
        assert normalize_confidence_value(250) == 1.0

    def test_negative_clamped_to_zero(self):
        assert normalize_confidence_value(-3) == 0.0

    def test_numeric_string(self):
        assert normalize_confidence_value("0.7") == 0.7
        assert normalize_confidence_value("70") == 0.7

    def test_garbage_is_zero(self):
        assert normalize_confidence_value("very confident") == 0.0
        assert normalize_confidence_value({}) == 0.0


# ── normalize_vision_ai_dict (field aliasing) ────────────────────────────────

class TestNormalizeVisionAIDict:
    def test_empty_dict_gets_defaults(self):
        out = normalize_vision_ai_dict({})
        assert out["name"] == "Clothing Item"
        assert out["category"] == "other"
        assert out["confidence"] == 0.0
        assert out["season"] == []
        assert out["occasions"] == []

    def test_category_aliases_merge_in_priority_order(self):
        assert normalize_vision_ai_dict({"garment_type": "jeans"})["category"] == "jeans"
        # explicit category wins over garment_type
        out = normalize_vision_ai_dict({"category": "tops", "garment_type": "jeans"})
        assert out["category"] == "tops"

    def test_color_aliases(self):
        assert normalize_vision_ai_dict({"primary_color": "navy"})["color"] == "navy"
        assert normalize_vision_ai_dict({"dominant_color": "red"})["color"] == "red"

    def test_occasion_string_splits_on_commas_and_semicolons(self):
        out = normalize_vision_ai_dict({"occasion": "work; casual, weekend"})
        assert out["occasions"] == ["work", "casual", "weekend"]

    def test_occasion_list_passthrough_drops_empties(self):
        out = normalize_vision_ai_dict({"occasions": ["Work", "", None, " gym "]})
        assert out["occasions"] == ["Work", "gym"]

    def test_season_tags_alias(self):
        out = normalize_vision_ai_dict({"season_tags": ["summer", "spring"]})
        assert out["season"] == ["summer", "spring"]

    def test_style_tags_falls_back_to_tags(self):
        out = normalize_vision_ai_dict({"tags": ["minimal", "street"]})
        assert out["style_tags"] == ["minimal", "street"]

    def test_confidence_score_alias(self):
        assert normalize_vision_ai_dict({"confidence_score": 90})["confidence"] == 0.9

    def test_eco_score_coerced_to_float_or_none(self):
        assert normalize_vision_ai_dict({"eco_score": "7"})["eco_score"] == 7.0
        assert normalize_vision_ai_dict({"eco_score": "n/a"})["eco_score"] is None


# ── parse_vision_ai_payload (end-to-end with validation) ─────────────────────

class TestParseVisionAIPayload:
    def test_happy_path(self):
        out = parse_vision_ai_payload(
            {
                "name": "  Blue Oxford Shirt ",
                "garment_type": "shirt",
                "color": "blue",
                "confidence": 92,
                "occasion": "work, smart casual",
            }
        )
        assert isinstance(out, NormalizedVisionAIOutput)
        assert out.name == "Blue Oxford Shirt"
        assert out.category == "tops"  # "shirt" alias coerced
        assert out.confidence == 0.92
        assert out.occasions == ["work", "smart casual"]

    def test_non_dict_payload_gets_safe_defaults(self):
        out = parse_vision_ai_payload("not json at all", source="bulk")
        assert out.name == "Clothing Item"
        assert out.category == "other"
        assert out.confidence == 0.0

    def test_unknown_category_coerces_to_other(self):
        out = parse_vision_ai_payload({"category": "spaceship"})
        assert out.category == "other"

    def test_blank_strings_become_none(self):
        out = parse_vision_ai_payload({"brand": "   ", "material": ""})
        assert out.brand is None
        assert out.material is None


# ── downstream dict shapes ────────────────────────────────────────────────────

class TestDownstreamDicts:
    def _normalized(self) -> NormalizedVisionAIOutput:
        return parse_vision_ai_payload(
            {
                "name": "Linen Shirt",
                "category": "tops",
                "color": "white",
                "season": ["summer"],
                "occasions": ["casual"],
                "confidence": 0.8,
            }
        )

    def test_legacy_upload_dict_mirrors_fields(self):
        d = normalized_to_legacy_upload_dict(self._normalized())
        assert d["name"] == "Linen Shirt"
        assert d["occasion"] == d["occasions"] == ["casual"]
        assert d["confidence"] == d["confidence_score"] == 0.8
        # optional strings become "" not None in the legacy shape
        assert d["brand"] == ""

    def test_bulk_api_dict_defaults_and_season_casing(self):
        d = normalized_to_bulk_api_dict(self._normalized())
        assert d["season_tags"] == ["Summer"]
        assert d["subcategory"] == "Unknown"
        assert d["fit"] == "Regular"
        assert d["occasion_tags"] == ["casual"]

    def test_bulk_api_dict_empty_occasions_default_to_casual(self):
        n = parse_vision_ai_payload({"name": "X", "category": "tops"})
        d = normalized_to_bulk_api_dict(n)
        assert d["occasion_tags"] == ["Casual"]

    def test_bulk_api_dict_raw_overrides(self):
        d = normalized_to_bulk_api_dict(
            self._normalized(),
            raw={"fit": "Slim", "secondary_colors": ["grey"], "warnings": ["low light"]},
        )
        assert d["fit"] == "Slim"
        assert d["secondary_colors"] == ["grey"]
        assert d["warnings"] == ["low light"]
