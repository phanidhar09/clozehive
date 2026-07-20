"""Shopping check → closet field mapping (Save / I bought it)."""

import pytest

from app.api.v1.intelligence.services.shopping_check_service import (
    _as_str_list,
    _closet_fields_from_analysis,
    _closet_owned_image_copy,
)


def test_as_str_list_normalizes_and_dedupes():
    assert _as_str_list(None) == []
    assert _as_str_list("Summer, Spring") == ["summer", "spring"]
    assert _as_str_list(["Casual", "casual", "Work"]) == ["casual", "work"]
    assert _as_str_list("") == []


def test_closet_fields_use_array_columns_not_json_strings():
    fields = _closet_fields_from_analysis(
        {
            "name": "Navy Blazer",
            "category": "jacket",
            "primary_color": "navy",
            "material": "wool",
            "pattern": "solid",
            "brand": "Theory",
            "season_tags": ["fall", "winter"],
            "occasion_tags": ["work", "formal"],
            "style_tags": ["tailored"],
            "description": "Sharp navy blazer",
            "source_price": "$249.00",
        },
        image_url="/uploads/shop-1.jpg",
    )

    assert fields["name"] == "Navy Blazer"
    assert fields["category"] == "outerwear"  # jacket → outerwear
    assert fields["color"] == "navy"
    assert fields["fabric"] == "wool"
    assert fields["season"] == ["fall", "winter"]
    assert fields["occasion"] == ["work", "formal"]
    assert fields["tags"] == ["tailored"]
    assert isinstance(fields["season"], list)
    assert isinstance(fields["occasion"], list)
    assert isinstance(fields["tags"], list)
    assert fields["price"] == 249.0
    assert fields["image_url"] == "/uploads/shop-1.jpg"
    assert fields["analysis_source"] == "shopping_check"


def test_closet_fields_fallback_name_and_category():
    fields = _closet_fields_from_analysis({}, image_url=None)
    assert fields["name"] == "Shopping Item"
    assert fields["category"] == "other"
    assert fields["season"] == []
    assert fields["price"] is None


def test_closet_fields_recover_name_and_category_from_myntra_url():
    fields = _closet_fields_from_analysis(
        {
            "name": "Buy",
            "category": "other",
            "source_title": "buy",
            "source_url": (
                "https://www.myntra.com/jeans/jack+%26+jones/"
                "jack--jones-men-bootcut-mid-rise-clean-look-stretchable-jeans/25917818/buy"
            ),
            "primary_color": "unknown",
            "material": "Unknown",
        },
        image_url="/uploads/myntra.jpg",
    )
    assert fields["name"] == "jack jones men bootcut mid rise clean look stretchable jeans"
    assert fields["category"] == "bottoms"
    assert fields["color"] is None
    assert fields["fabric"] is None
    assert fields["image_url"] == "/uploads/myntra.jpg"


@pytest.mark.asyncio
async def test_closet_owned_image_copy_persists_new_file(monkeypatch):
    source = "/uploads/source.png"
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    import app.core.upload_service as upload_mod

    monkeypatch.setattr(upload_mod, "read_upload_bytes", lambda url: png)

    async def fake_persist(image_bytes, content_type, filename):
        assert image_bytes.startswith(b"\x89PNG")
        assert content_type == "image/png"
        return "/uploads/closet-owned.png"

    monkeypatch.setattr(upload_mod, "persist_upload", fake_persist)

    closet_url, original = await _closet_owned_image_copy(source)
    assert closet_url == "/uploads/closet-owned.png"
    assert original == source


@pytest.mark.asyncio
async def test_closet_owned_image_copy_falls_back_on_missing_source():
    closet_url, original = await _closet_owned_image_copy(None)
    assert closet_url is None
    assert original is None
