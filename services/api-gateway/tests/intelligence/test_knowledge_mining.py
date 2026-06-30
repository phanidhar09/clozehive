"""The learned-knowledge aggregator turns real usage into a grounded KB doc — safely."""

from __future__ import annotations

from app.api.v1.intelligence.services.knowledge_mining_service import (
    is_successful_history,
    summarize_pairings,
)


def test_is_successful_history():
    assert is_successful_history(True, False, None)  # saved
    assert is_successful_history(False, True, None)  # worn
    assert is_successful_history(False, False, 90)  # high score
    assert not is_successful_history(False, False, 50)  # mediocre, not kept
    assert not is_successful_history(False, False, None)  # no signal


def _outfit(*items: tuple[str, str]) -> list[dict]:
    return [{"category": c, "color": col} for c, col in items]


# A neutral-anchored, mostly top+bottom+shoe corpus.
_CORPUS = [
    _outfit(("tops", "white"), ("bottoms", "navy"), ("shoes", "brown")),
    _outfit(("tops", "black"), ("bottoms", "grey")),
    _outfit(("tops", "white"), ("bottoms", "black"), ("shoes", "white")),
] * 8  # 24 outfits


def test_returns_none_when_too_few_outfits():
    assert summarize_pairings(_CORPUS[:5], num_users=10) is None


def test_returns_none_when_too_few_users():
    assert summarize_pairings(_CORPUS, num_users=2) is None


def test_skips_single_item_outfits():
    singles = [_outfit(("tops", "white"))] * 50
    assert summarize_pairings(singles, num_users=10) is None


def test_emits_learned_doc_with_enough_data():
    doc = summarize_pairings(_CORPUS, num_users=6)
    assert doc is not None
    assert doc["category"] == "learned"
    assert doc["source"] == "user_data"
    assert doc["title"]
    # Grounded, anonymised content — references aggregate counts, not users/items.
    assert "24" in doc["content"]  # outfit count
    assert "6 users" in doc["content"]
    # Neutral-anchored corpus should be reported as neutral-dominant.
    assert "neutral" in doc["content"].lower()
    # Most-worn pairing top+bottom should surface.
    assert "top+bottom" in doc["content"]


def test_accent_heavy_corpus_reports_higher_accent_share():
    # Two saturated colours together in every outfit.
    accent = [_outfit(("tops", "red"), ("bottoms", "green"))] * 30
    doc = summarize_pairings(accent, num_users=8)
    assert doc is not None
    # accent-accent share should be high here vs the neutral corpus.
    assert "pair two saturated colours" in doc["content"]
