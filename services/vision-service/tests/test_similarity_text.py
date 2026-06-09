"""Tests for the embedding text builder and the no-API-key embedding fallback.

_item_to_text must mirror closet-service's item_to_embedding_text() — both
services write vectors into the same closet_items.embedding space, so any
drift here silently degrades similarity search.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services import similarity_service
from app.services.similarity_service import _item_to_text, generate_item_embedding


def _item(**overrides) -> SimpleNamespace:
    base = dict(
        id="00000000-0000-0000-0000-000000000001",
        name="Blue Oxford",
        category="tops",
        subcategory="shirt",
        color="blue",
        brand=None,
        notes=None,
        description=None,
        fabric=None,
        material=None,
        pattern=None,
        season=[],
        occasion=[],
        tags=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestItemToText:
    def test_basic_descriptor_uses_color_and_subcategory(self):
        text = _item_to_text(_item())
        assert "blue shirt" in text
        assert "called 'Blue Oxford'" in text
        assert text.endswith(".")

    def test_name_matching_type_not_repeated(self):
        text = _item_to_text(_item(name="Shirt"))
        assert "called" not in text

    def test_solid_and_unknown_patterns_omitted(self):
        assert "Pattern" not in _item_to_text(_item(pattern="solid"))
        assert "Pattern" not in _item_to_text(_item(pattern="Unknown"))
        assert "Pattern: striped" in _item_to_text(_item(pattern="striped"))

    def test_brand_season_occasion_tags_included(self):
        text = _item_to_text(
            _item(brand="Uniqlo", season=["summer"], occasion=["work"], tags=["minimal"])
        )
        assert "Brand: Uniqlo" in text
        assert "Suitable for summer" in text
        assert "Worn for work" in text
        assert "Style: minimal" in text

    def test_falls_back_to_category_when_no_subcategory(self):
        text = _item_to_text(_item(subcategory=None, name="Tee"))
        assert "blue tops" in text

    def test_material_used_when_no_fabric(self):
        text = _item_to_text(_item(material="linen"))
        assert "linen" in text


class TestEmbeddingFallback:
    async def test_returns_zero_vector_without_api_key(self, monkeypatch):
        # Force the no-key path regardless of local env.
        monkeypatch.setattr(similarity_service.settings, "openai_api_key", "")
        vector = await generate_item_embedding(_item())
        assert len(vector) == 1536
        assert all(v == 0.0 for v in vector)
