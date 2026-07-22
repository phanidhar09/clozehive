"""Unit tests for purchase-gap grounding of LLM ``missing_pieces``.

Grounding keeps a recognized wardrobe category while allowing particular item
phrases (e.g. "brown suede Chelsea boots"). Invented slots with no category
anchor are still dropped.

Run with:
    cd services/api-gateway
    DATABASE_URL="sqlite+aiosqlite:///:memory:" JWT_SECRET="test-secret-32-chars-minimum!!" \
      .venv/bin/pytest tests/intelligence/test_purchase_gap_grounding.py -v
"""

from __future__ import annotations

import pytest

from app.api.v1.intelligence.services.purchase_gap_service import (
    _detect_closet_gaps,
    _normalize_missing_piece,
    _normalize_outfit_type,
    _specific_item_for,
)


@pytest.mark.parametrize(
    ("piece", "expected_category", "expected_label"),
    [
        ("outerwear", "outerwear", "outerwear"),
        ("footwear", "shoes", "footwear"),
        ("belt", "accessories", "belt"),
        ("Belt", "accessories", "belt"),
        ("  jacket  ", "outerwear", "jacket"),
        ("a belt", "accessories", "belt"),
        ("the jacket", "outerwear", "jacket"),
        ("dress", "dresses", "dress"),
        ("brown suede chelsea boots", "shoes", "brown suede chelsea boots"),
        ("navy blazer", "outerwear", "navy blazer"),
        ("black leather belt", "accessories", "black leather belt"),
    ],
)
def test_recognized_pieces_map_to_canonical_category(
    piece: str, expected_category: str, expected_label: str
) -> None:
    result = _normalize_missing_piece(piece)
    assert result is not None
    category, label = result
    assert category == expected_category
    assert label == expected_label


@pytest.mark.parametrize(
    "piece",
    [
        "unicorn cape",
        "",
        "   ",
        "something",
        "a statement necklace with turquoise stones",  # no grounded alias
    ],
)
def test_ungrounded_pieces_are_dropped(piece: str) -> None:
    assert _normalize_missing_piece(piece) is None


def test_normalize_outfit_type_rejects_versatile():
    assert _normalize_outfit_type("versatile") is None
    assert _normalize_outfit_type("all-season") is None
    assert _normalize_outfit_type("Formal Dinner") == "formal dinner"


def test_specific_item_for_occasion_not_versatile():
    item = _specific_item_for("shoes", "formal dinner", "shoes")
    assert "oxford" in item or "loafer" in item
    assert "versatile" not in item.lower()


def test_specific_item_keeps_particular_phrase():
    assert (
        _specific_item_for("shoes", "casual", "brown suede chelsea boots")
        == "brown suede chelsea boots"
    )


def test_structural_gaps_name_item_and_outfit_type():
    gaps = _detect_closet_gaps(
        [{"category": "tops", "occasion": ["work"]}],
        user_id="user",
    )
    shoe_gaps = [g for g in gaps if g["missing_category"] == "shoes"]
    assert shoe_gaps, "expected a shoes structural gap"
    gap = shoe_gaps[0]
    attrs = gap["suggested_attributes"]
    assert attrs["item"]
    assert "versatile" not in attrs["item"].lower()
    assert attrs["outfit_type"]
    assert gap["missing_occasion"]
    assert "outfits" in gap["reason"].lower()
    assert "versatile" not in gap["reason"].lower()
