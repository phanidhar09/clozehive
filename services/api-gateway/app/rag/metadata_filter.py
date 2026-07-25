"""Metadata pre-filtering for RAG retrieval — hard constraints applied *before*
ranking, as distinct from the soft boosts in :mod:`app.rag.rerank`.

Why pre-filter at all
─────────────────────
A bi-encoder will happily return a men's-tailoring passage for a women's-outfit
query because the two are "semantically close". Downstream reranking can only
reorder what retrieval hands it — by then a wrong-audience document has already
displaced a right-audience one from the candidate pool. A metadata pre-filter
removes documents whose *structured* metadata contradicts a known query
constraint before they ever compete for a slot.

Gender is the cleanest such constraint in the fashion KB: menswear vs womenswear
is a genuine partition, while ``unisex`` / untagged docs belong to everyone.
Formality and region are ordinal / soft signals and are deliberately left to the
reranker rather than filtered here.

Shape-agnostic
──────────────
The helpers are pure and dependency-free so they can filter either half of hybrid
retrieval:

  - the in-memory **lexical** corpus, where ``gender`` sits at the top level;
  - a **pgvector** row, where ``gender`` is nested in the ``tags`` JSONB
    (see ``fashion_rag_service._build_tags_payload``).

The dense (pgvector) half additionally supports a true index-time pre-filter at
the SQL level via ``pgvector_cosine_search(tags_gender=...)``; this module covers
the lexical half and any Python-side candidate pool so both halves of the hybrid
are filtered consistently before fusion.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

# Corpus gender partition. Only these two canonical audiences ever filter anything
# out; ``unisex`` / None documents are audience-neutral and always pass.
_MEN = frozenset({"men", "man", "male", "masculine", "mens", "menswear"})
_WOMEN = frozenset({"women", "woman", "female", "feminine", "womens", "womenswear"})

# Canonical value the fashion corpus stores for audience-neutral documents.
UNISEX = "unisex"


def canonical_gender(value: str | None) -> str | None:
    """Map a free-form gender string to ``"men"``, ``"women"``, or ``None``.

    ``None`` means "no usable binary signal" — non-binary, custom, ``unisex``,
    empty, or unrecognised values all return ``None`` so retrieval stays
    unfiltered and audience-neutral rather than guessing an audience.
    """
    if not value:
        return None
    v = value.strip().lower()
    if v in _MEN:
        return "men"
    if v in _WOMEN:
        return "women"
    return None


def gender_allows(doc_gender: str | None, target: str | None) -> bool:
    """Whether a document tagged ``doc_gender`` may serve a ``target``-audience query.

    Passes (any one sufficient):
      - ``target`` is ``None``            → no constraint, everything passes;
      - ``doc_gender`` is None/unisex/other → audience-neutral, serves everyone;
      - the two canonical genders match.
    """
    if target is None:
        return True
    dg = canonical_gender(doc_gender)
    if dg is None:  # unisex / untagged / unrecognised → neutral, serves everyone
        return True
    return dg == target


def gender_of_row(doc: dict[str, Any]) -> str | None:
    """Read a document's gender from either shape used across the pipeline.

    Lexical corpus docs carry ``gender`` at the top level; seeded pgvector rows
    nest it inside the ``tags`` JSONB.
    """
    top = doc.get("gender")
    if isinstance(top, str) and top:
        return top
    tags = doc.get("tags")
    if isinstance(tags, dict):
        nested = tags.get("gender")
        if isinstance(nested, str) and nested:
            return nested
    return None


def filter_by_gender[T](
    docs: Iterable[T],
    target: str | None,
    *,
    gender_of: Callable[[T], str | None] = gender_of_row,  # type: ignore[assignment]
) -> list[T]:
    """Drop documents whose gender contradicts ``target``; preserve input order.

    A no-op (returns the input as a list) when ``target`` is ``None``.
    """
    if target is None:
        return list(docs)
    return [d for d in docs if gender_allows(gender_of(d), target)]
