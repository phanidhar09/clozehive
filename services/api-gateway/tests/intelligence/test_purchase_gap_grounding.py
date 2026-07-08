"""Unit tests for purchase-gap grounding of LLM ``missing_pieces``.

The outfit-analysis LLM returns a free-text ``missing_pieces`` field that flows
straight into persisted purchase gaps. These tests pin the allowlist behavior
that grounds each value to a canonical category and drops hallucinated values.

Run with:
    cd services/api-gateway
    DATABASE_URL="sqlite+aiosqlite:///:memory:" JWT_SECRET="test-secret-32-chars-minimum!!" \
      .venv/bin/pytest tests/intelligence/test_purchase_gap_grounding.py -v
"""

from __future__ import annotations

import pytest

from app.api.v1.intelligence.services.purchase_gap_service import (
    _normalize_missing_piece,
)


@pytest.mark.parametrize(
    ("piece", "expected_category", "expected_label"),
    [
        ("outerwear", "outerwear", "outerwear"),
        ("footwear", "shoes", "footwear"),
        ("belt", "accessories", "belt"),
        ("Belt", "accessories", "belt"),  # case-insensitive
        ("  jacket  ", "outerwear", "jacket"),  # whitespace-trimmed
        ("a belt", "accessories", "belt"),  # leading article stripped
        ("the jacket", "outerwear", "jacket"),
        ("dress", "dresses", "dress"),
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
        "brown suede Chelsea boots",  # specific item name, not a category
        "vintage band tee from 2003",
        "a statement necklace with turquoise stones",
        "unicorn cape",  # invented slot
        "",
        "   ",
        "something",
    ],
)
def test_hallucinated_or_specific_pieces_are_dropped(piece: str) -> None:
    assert _normalize_missing_piece(piece) is None
