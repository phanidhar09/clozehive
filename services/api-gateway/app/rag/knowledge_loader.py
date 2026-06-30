"""Load the fashion-knowledge seed corpus from versioned YAML data files.

The corpus lives in ``app/rag/knowledge/*.yaml`` (one file per category) instead of
being hard-coded in Python, so it can grow without code changes and non-engineers can
contribute. Each file has the shape::

    category: <name>
    documents:
      - title: <unique title>
        content: <prose>
        occasion: <str|null>
        season: <str|null>
        tags: [<str>, ...]
        gender: unisex|men|women        # filterable metadata, folded into the tags JSONB
        formality_level: <0-4|null>
        region: <str|null>
        source: curated|generated|user_data|licensed

``taxonomy.yaml`` is the growth outline, not a corpus file — it is skipped.

The loader is defensive: a malformed file is logged and skipped rather than breaking
seeding, documents missing ``title``/``content`` are dropped, and titles are
de-duplicated (first occurrence wins) since seeding keys on title.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

from app.core.logging import get_logger

logger = get_logger("knowledge_loader")

_KNOWLEDGE_DIR = pathlib.Path(__file__).parent / "knowledge"
# Files that are not corpus documents.
_SKIP_FILES = {"taxonomy.yaml"}

# Metadata carried alongside the core fields (stored in the tags JSONB at seed time).
_META_KEYS = ("gender", "formality_level", "region", "source")


def _coerce_doc(raw: dict[str, Any], category: str) -> dict[str, Any] | None:
    title = raw.get("title")
    content = raw.get("content")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(content, str) or not content.strip():
        return None
    doc: dict[str, Any] = {
        "title": title.strip(),
        "content": content.strip(),
        "category": raw.get("category") or category,
        "season": raw.get("season"),
        "occasion": raw.get("occasion"),
        "tags": list(raw.get("tags") or []),
    }
    for key in _META_KEYS:
        if raw.get(key) is not None:
            doc[key] = raw[key]
    return doc


def load_seed_documents() -> list[dict[str, Any]]:
    """Return all corpus documents from the knowledge data files.

    Stable order (filename, then file order). Duplicate titles are dropped so the
    idempotent, title-keyed seeding in ``fashion_rag_service.ensure_seeded`` stays correct.
    """
    if not _KNOWLEDGE_DIR.is_dir():
        logger.warning("knowledge_dir_missing", path=str(_KNOWLEDGE_DIR))
        return []

    docs: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for path in sorted(_KNOWLEDGE_DIR.glob("*.yaml")):
        if path.name in _SKIP_FILES:
            continue
        try:
            payload = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as exc:
            logger.warning("knowledge_file_parse_failed", file=path.name, error=str(exc))
            continue
        if not isinstance(payload, dict):
            logger.warning("knowledge_file_bad_shape", file=path.name)
            continue
        category = str(payload.get("category") or path.stem)
        entries = payload.get("documents")
        if not isinstance(entries, list):
            logger.warning("knowledge_file_no_documents", file=path.name)
            continue
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            doc = _coerce_doc(raw, category)
            if doc is None:
                logger.warning("knowledge_doc_invalid", file=path.name, title=raw.get("title"))
                continue
            if doc["title"] in seen_titles:
                logger.warning("knowledge_doc_duplicate_title", title=doc["title"])
                continue
            seen_titles.add(doc["title"])
            docs.append(doc)

    logger.info("knowledge_corpus_loaded", count=len(docs))
    return docs
