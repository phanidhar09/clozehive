"""Reciprocal Rank Fusion (RRF) for hybrid retrieval.

Different retrievers (dense vector, BM25 lexical) return scores on
incomparable scales — cosine similarity in [0, 1] vs. unbounded BM25. Trying to
normalise and add them is fragile. RRF sidesteps the problem by fusing on
*rank* instead of score:

    RRF(d) = Σ_r  weight_r / (k + rank_r(d))

where ``rank_r(d)`` is d's 1-based position in retriever r's list (a document
absent from a list contributes nothing). ``k`` (default 60, per the original
Cormack et al. paper) damps the contribution of low ranks so the head of each
list dominates. The result is a single robust ordering that rewards documents
surfaced by *multiple* retrievers.

This module is pure and retriever-agnostic: give it ranked lists and a key
function, get back a fused ordering of keys with scores.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

DEFAULT_K = 60


def reciprocal_rank_fusion[T](
    ranked_lists: Sequence[Sequence[T]],
    *,
    key: Callable[[T], str],
    weights: Sequence[float] | None = None,
    k: int = DEFAULT_K,
) -> list[tuple[str, float]]:
    """Fuse several ranked lists into one ranking of keys.

    Args:
        ranked_lists: each inner sequence is one retriever's results, already
            ordered best-first.
        key: extracts a stable identity (e.g. normalised title) from an item so
            the same document from different retrievers fuses together.
        weights: optional per-list weights (defaults to 1.0 each). Length must
            match ``ranked_lists``.
        k: RRF damping constant. Larger k flattens the rank contribution.

    Returns:
        ``(key, fused_score)`` tuples sorted by descending score. Ties are
        broken by key for deterministic output.
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    elif len(weights) != len(ranked_lists):
        raise ValueError("weights length must match ranked_lists length")

    scores: dict[str, float] = {}
    for lst, weight in zip(ranked_lists, weights):
        for rank, item in enumerate(lst, start=1):
            item_key = key(item)
            scores[item_key] = scores.get(item_key, 0.0) + weight / (k + rank)

    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
