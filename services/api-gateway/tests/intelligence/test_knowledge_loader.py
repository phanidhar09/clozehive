"""The YAML knowledge corpus loads, validates, and feeds the fashion RAG seed."""

from __future__ import annotations

from app.rag.knowledge_loader import load_seed_documents


def test_loads_full_corpus_with_required_fields():
    docs = load_seed_documents()
    # The 22 migrated docs plus the regional and fabric sets.
    assert len(docs) >= 30
    for d in docs:
        assert d["title"].strip()
        assert d["content"].strip()
        assert d["category"]
        assert isinstance(d["tags"], list)


def test_fabric_category_present():
    cats = {d["category"] for d in load_seed_documents()}
    assert "fabric" in cats
    assert "regional" in cats


def test_titles_are_unique():
    docs = load_seed_documents()
    titles = [d["title"] for d in docs]
    assert len(titles) == len(set(titles))


def test_includes_migrated_and_new_regional_docs():
    titles = {d["title"] for d in load_seed_documents()}
    assert "Color Matching Fundamentals" in titles  # migrated
    assert "South Asian Festive & Ethnic Wear Guide" in titles  # new


def test_regional_docs_carry_filter_metadata():
    docs = load_seed_documents()
    regional = next(d for d in docs if d["title"] == "Modest Dressing Principles (Cross-Cultural)")
    assert regional["region"] == "global"
    assert regional["source"] == "curated"


def test_taxonomy_file_is_not_seeded():
    titles = {d["title"] for d in load_seed_documents()}
    # taxonomy.yaml has no `documents:` list, so nothing from it should appear.
    assert not any("taxonomy" in t.lower() for t in titles)


def test_seed_payload_packs_metadata_into_tags_jsonb():
    from app.api.v1.intelligence.services.fashion_rag_service import _build_tags_payload

    payload = _build_tags_payload(
        {"tags": ["a", "b"], "gender": "unisex", "region": "south asia", "source": "curated"}
    )
    assert payload["tags"] == ["a", "b"]
    assert payload["region"] == "south asia"
    assert payload["source"] == "curated"
    # Absent metadata keys are omitted, not stored as null.
    assert "formality_level" not in payload
