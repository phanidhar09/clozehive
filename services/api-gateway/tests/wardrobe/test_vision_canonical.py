"""Tests for vision AI normalization and canonical preview schema."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.v1.wardrobe.schemas.vision_canonical import (
    NormalizedVisionAIOutput,
    normalize_confidence_value,
    normalize_vision_ai_dict,
    normalized_to_bulk_api_dict,
    normalized_to_legacy_upload_dict,
    parse_vision_ai_payload,
    vision_analysis_item_to_normalized,
)


class TestNormalizeConfidenceValue:
    def test_none(self):
        assert normalize_confidence_value(None) == 0.0

    def test_unit_float(self):
        assert normalize_confidence_value(0.85) == 0.85

    def test_percentage(self):
        assert abs(normalize_confidence_value(85) - 0.85) < 1e-9

    def test_clamp_high(self):
        assert normalize_confidence_value(150) == 1.0

    def test_invalid(self):
        assert normalize_confidence_value("nope") == 0.0


class TestParseVisionValidOpenAIJson:
    def test_schema_fields(self):
        raw = {
            "name": "White Tee",
            "category": "tops",
            "color": "white",
            "brand": "Nike",
            "material": "cotton",
            "pattern": "solid",
            "season": ["summer"],
            "occasion": ["casual", "sport"],
            "notes": "Basic tee",
            "confidence": 0.92,
            "eco_score": 7.5,
        }
        n = parse_vision_ai_payload(raw, source="openai")
        assert n.name == "White Tee"
        assert n.category == "tops"
        assert n.color == "white"
        assert n.material == "cotton"
        assert n.season == ["summer"]
        assert set(n.occasions) == {"casual", "sport"}
        assert n.description == "Basic tee"
        assert abs(n.confidence - 0.92) < 1e-9
        assert n.eco_score == 7.5


class TestParseVisionAliases:
    def test_garment_type_and_color_primary(self):
        n = parse_vision_ai_payload(
            {"garment_type": "outerwear", "color_primary": "Navy", "name": "Coat"},
            source="openai",
        )
        assert n.category == "outerwear"
        assert n.color == "Navy"

    def test_occasion_tags_and_season_tags(self):
        n = parse_vision_ai_payload(
            {
                "name": "Jeans",
                "category": "bottoms",
                "occasion_tags": ["Casual"],
                "season_tags": ["fall", "winter"],
            },
            source="bulk",
        )
        assert n.occasions == ["Casual"]
        assert n.season == ["fall", "winter"]


class TestPartialJson:
    def test_missing_name_category(self):
        n = parse_vision_ai_payload({"color": "red"}, source="openai")
        assert n.name == "Clothing Item"
        assert n.category == "other"
        assert n.color == "red"

    def test_empty_dict(self):
        n = parse_vision_ai_payload({}, source="openai")
        assert n.name == "Clothing Item"
        assert n.occasions == []


class TestMalformedJson:
    def test_non_dict(self):
        n = parse_vision_ai_payload(["not", "a", "dict"], source="openai")
        assert n.category == "other"
        assert n.confidence == 0.0

    def test_invalid_category_string_maps_to_other(self):
        n = parse_vision_ai_payload({"category": "%%%invalid%%%", "name": "X"}, source="openai")
        assert n.category == "other"


class TestNormalizedExports:
    def test_legacy_upload_dict_has_occasion_keys(self):
        n = NormalizedVisionAIOutput(name="A", category="tops", occasions=["work"], season=["spring"])
        d = normalized_to_legacy_upload_dict(n)
        assert d["occasion"] == ["work"]
        assert d["occasions"] == ["work"]
        assert d["material"] == ""

    def test_bulk_api_primary_color(self):
        n = parse_vision_ai_payload({"name": "B", "category": "shoes", "primary_color": "Black"}, source="bulk")
        b = normalized_to_bulk_api_dict(n)
        assert b["primary_color"] == "Black"
        assert b["occasion_tags"]


class TestMultipleDetectionsIndependent:
    def test_two_pipeline_style_objects(self):
        a = vision_analysis_item_to_normalized(
            SimpleNamespace(
                item_id="1",
                name="Shirt",
                category="tops",
                subcategory=None,
                primary_color="Blue",
                brand=None,
                material="linen",
                pattern=None,
                season=["summer"],
                occasions=["casual"],
                description=None,
                confidence_score=0.9,
                style_tags=[],
            )
        )
        b = vision_analysis_item_to_normalized(
            SimpleNamespace(
                item_id="2",
                name="Pants",
                category="bottoms",
                subcategory="Jeans",
                primary_color=None,
                brand=None,
                material="denim",
                pattern=None,
                season=[],
                occasions=["casual"],
                description="Slim fit",
                confidence_score=0.75,
                style_tags=["minimal"],
            )
        )
        assert a.name == "Shirt" and a.category == "tops"
        assert b.name == "Pants" and b.category == "bottoms"
        assert b.material == "denim"
        assert b.description == "Slim fit"


class TestNormalizeVisionAiDictRaw:
    def test_merge(self):
        d = normalize_vision_ai_dict(
            {"garment_type": "dresses", "confidence_score": 95, "occasion": "formal, party"}
        )
        assert d["occasions"] == ["formal", "party"]
        assert abs(float(d["confidence"]) - 0.95) < 1e-9
