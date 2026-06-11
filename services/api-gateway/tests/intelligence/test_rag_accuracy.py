"""Unit tests for RAG query builder and metadata reranking."""

from __future__ import annotations

from app.rag.query_builder import (
    build_closet_rag_query,
    build_fashion_knowledge_query,
    extract_keywords,
    infer_query_signals,
)
from app.rag.rerank import rerank_fashion_documents, rerank_outfit_history


def test_infer_wedding_occasion_from_query():
    signals = infer_query_signals("What should I wear to a summer wedding?")
    assert signals["occasion"] == "wedding"
    assert signals["season"] == "summer"


def test_build_closet_rag_query_natural_language():
    q = build_closet_rag_query(
        "Need something polished for a client dinner",
        occasion="business casual",
        mood="confident",
    )
    assert "client dinner" in q
    assert "Occasion: business casual" in q
    assert "Mood: confident" in q


def test_build_fashion_knowledge_query_infers_context():
    q = build_fashion_knowledge_query("pack for rainy trip to London")
    assert "rain" in q.lower() or "travel" in q.lower()


def test_extract_keywords_skips_stop_words():
    keywords = extract_keywords("What should I wear for a wedding reception?")
    assert "wedding" in keywords
    assert "what" not in keywords


def test_rerank_fashion_docs_boosts_occasion_match():
    docs = [
        {"title": "Casual Guide", "content": "...", "occasion": "casual", "relevance_score": 0.72},
        {"title": "Wedding Guest Guide", "content": "...", "occasion": "wedding", "relevance_score": 0.70},
    ]
    ranked = rerank_fashion_documents(docs, occasion="wedding")
    assert ranked[0]["title"] == "Wedding Guest Guide"


def test_rerank_outfit_history_boosts_worn_outfits():
    records = [
        {"occasion": "casual", "similarity_score": 0.75, "was_worn": False, "was_saved": False},
        {"occasion": "casual", "similarity_score": 0.72, "was_worn": True, "was_saved": True, "matching_score": 85},
    ]
    ranked = rerank_outfit_history(records, occasion="casual")
    assert ranked[0]["was_worn"] is True
