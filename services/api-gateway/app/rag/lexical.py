"""Dependency-free BM25 lexical retriever over the fashion knowledge corpus.

Vector search blurs exact terms — brand names, fabric words ("linen", "gore-tex"),
rare tokens, and negations all get smeared into a dense neighbourhood. A lexical
retriever recovers them by scoring literal term overlap. Running both and fusing
(see :mod:`app.rag.fusion`) is the whole point of hybrid retrieval.

We implement Okapi BM25 in ~40 lines rather than pulling in ``rank_bm25`` because:

- the corpus is small and static (seeded from ``app/rag/knowledge/*.yaml``), so a
  plain in-memory index rebuilt once at import is more than fast enough;
- it is fully deterministic with no network/DB, which lets the retrieval eval
  suite score it hermetically (see ``evals/datasets/retrieval.yaml``);
- it keeps the dependency surface flat.

Output rows are shaped to match the vector path
(``fashion_rag_service.search_fashion_knowledge``) so the two lists fuse cleanly:
``id``/``title``/``content``/``category``/``season``/``occasion`` plus a
``lexical_score`` (raw BM25 score, unbounded ≥ 0). ``id`` is empty for lexical
hits — the seed corpus has no DB id until it is fetched; fusion prefers the
vector row's id when a document appears in both lists.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

# BM25 free parameters — standard defaults. k1 controls term-frequency
# saturation; b controls length normalisation.
_K1 = 1.5
_B = 0.75

# A deliberately small stopword set. BM25's idf already discounts common words,
# so we only strip the highest-frequency function words that add pure noise.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "is",
        "it",
        "with",
        "as",
        "by",
        "be",
        "are",
        "this",
        "that",
        "from",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords and 1-char tokens removed."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) > 1 and t not in _STOPWORDS]


def _document_text(doc: dict[str, Any]) -> str:
    """Concatenate the searchable fields of a corpus document.

    Title is repeated so a title-term match outweighs the same term buried in
    body prose — titles are the most intent-bearing field in this corpus.
    """
    parts = [
        doc.get("title", ""),
        doc.get("title", ""),
        doc.get("content", ""),
        doc.get("occasion") or "",
        doc.get("season") or "",
        " ".join(str(t) for t in (doc.get("tags") or [])),
        str(doc.get("category") or ""),
    ]
    return " ".join(p for p in parts if p)


class LexicalIndex:
    """In-memory BM25 index over a fixed list of corpus documents."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self._docs = documents
        self._doc_tokens: list[list[str]] = [_tokenize(_document_text(d)) for d in documents]
        self._doc_len: list[int] = [len(toks) for toks in self._doc_tokens]
        self._term_freqs: list[Counter[str]] = [Counter(toks) for toks in self._doc_tokens]

        n = len(documents)
        self._n = n
        self._avgdl = (sum(self._doc_len) / n) if n else 0.0

        # Document frequency per term, then precompute idf.
        df: Counter[str] = Counter()
        for tf in self._term_freqs:
            df.update(tf.keys())
        # BM25+ idf variant (+1 inside the log) keeps idf strictly non-negative,
        # so a term appearing in most documents can never drag a score negative.
        self._idf: dict[str, float] = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to ``limit`` documents ranked by BM25, highest first.

        ``category`` restricts scoring to documents in that category. Documents
        with a zero score (no query-term overlap) are never returned.
        """
        q_terms = _tokenize(query)
        if not q_terms or self._n == 0:
            return []

        scored: list[tuple[float, int]] = []
        for i, doc in enumerate(self._docs):
            if category and doc.get("category") != category:
                continue
            score = self._score_doc(i, q_terms)
            if score > 0:
                scored.append((score, i))

        scored.sort(key=lambda x: x[0], reverse=True)
        out: list[dict[str, Any]] = []
        for score, i in scored[:limit]:
            doc = self._docs[i]
            out.append(
                {
                    "id": str(doc.get("id") or ""),
                    "title": doc.get("title", ""),
                    "content": doc.get("content", ""),
                    "category": doc.get("category"),
                    "season": doc.get("season"),
                    "occasion": doc.get("occasion"),
                    # Carried through so the metadata pre-filter can read audience
                    # off the lexical half (app.rag.metadata_filter).
                    "gender": doc.get("gender"),
                    "lexical_score": round(float(score), 4),
                }
            )
        return out

    def _score_doc(self, doc_idx: int, q_terms: list[str]) -> float:
        tf = self._term_freqs[doc_idx]
        dl = self._doc_len[doc_idx]
        denom_len = _K1 * (1 - _B + _B * (dl / self._avgdl if self._avgdl else 0.0))
        score = 0.0
        for term in q_terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = self._idf.get(term, 0.0)
            score += idf * (freq * (_K1 + 1)) / (freq + denom_len)
        return score


def build_lexical_index(documents: list[dict[str, Any]]) -> LexicalIndex:
    """Construct a BM25 index. Cheap — safe to call once at module import."""
    return LexicalIndex(documents)
