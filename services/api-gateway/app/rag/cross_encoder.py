"""LLM cross-encoder reranking — the precision stage after hybrid retrieval.

A bi-encoder (used for vector retrieval) embeds the query and each document
*independently*, so it can only ever measure their positions in a shared space.
A cross-encoder reads the query and a passage *together* and scores true
relevance — the single biggest precision lever in a RAG pipeline.

We run that joint scoring through the existing LLM stack (``ai_service.chat`` on
the cheap/fast tier) rather than a local transformer: it needs no new heavyweight
dependency on the single web dyno, and it reuses the token/cost telemetry and
pricing already wired into every generation. It scores all candidates in one
call (listwise), so cost is one small-model request per reranked query, not one
per document.

Contract — this stage is **pure reordering**:

- it never adds, drops, or edits documents; the output is a permutation of the
  input plus a ``rerank_score`` annotation;
- on *any* failure (disabled, too few candidates, LLM error, malformed output,
  out-of-range ids) it returns the input order unchanged. A reranker that can
  silently lose a grounded document is worse than no reranker, so every failure
  degrades to the retrieval order the caller already trusts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.analytics import LLMTelemetry

logger = get_logger("rag.cross_encoder")

_SYSTEM_PROMPT = (
    "You are a relevance ranking engine. Given a user query and a numbered list "
    "of candidate passages, score how well each passage answers the query on a "
    "scale from 0 (irrelevant) to 10 (directly answers it). Judge relevance only "
    "— ignore writing quality and length. Respond with JSON of the exact form "
    '{"scores": [{"id": <passage number>, "score": <0-10>}, ...]} covering every '
    "passage id exactly once. Output nothing but the JSON."
)

# A default below the 0-10 range so any passage the model failed to score sorts
# beneath every scored one while keeping its original relative order.
_UNSCORED = -1.0


def is_enabled() -> bool:
    return bool(get_settings().rag_cross_encoder_enabled)


async def rerank(
    query: str,
    documents: list[dict[str, Any]],
    *,
    text_of: Callable[[dict[str, Any]], str],
    top_n: int | None = None,
    passage_chars: int = 500,
    telemetry: LLMTelemetry | None = None,
) -> list[dict[str, Any]]:
    """Reorder ``documents`` by LLM-judged relevance to ``query``.

    Args:
        query: the natural-language query the documents were retrieved for.
        documents: retrieval hits, best-first. Returned reordered, never changed.
        text_of: extracts the passage text to judge from a document.
        top_n: only the first ``top_n`` documents are reranked; the remainder are
            appended in their original order (they were already the tail). Defaults
            to the configured ``rag_cross_encoder_top_n``.
        passage_chars: per-passage character budget sent to the model.
        telemetry: optional call-site context for token/cost capture.

    Returns:
        A permutation of ``documents``. Reranked docs carry a ``rerank_score``
        (0-10) key; on any short-circuit the input list is returned unchanged.
    """
    settings = get_settings()
    if not settings.rag_cross_encoder_enabled or len(documents) <= 1:
        return documents

    n = top_n if top_n is not None else int(settings.rag_cross_encoder_top_n)
    candidates = documents[:n]
    tail = documents[n:]
    if len(candidates) <= 1:
        return documents

    passages = "\n".join(
        f"[{i}] {text_of(doc)[:passage_chars].strip()}" for i, doc in enumerate(candidates)
    )
    user_prompt = f"Query: {query.strip()}\n\nPassages:\n{passages}"

    try:
        # Lazy import keeps app.rag free of an app.api import cycle.
        from app.api.v1.intelligence.services import ai_service

        raw = await ai_service.chat(
            [{"role": "user", "content": user_prompt}],
            _SYSTEM_PROMPT,
            use_json_mode=True,
            temperature=0.0,
            max_tokens=256,
            model=settings.rag_cross_encoder_model or settings.openai_model_small,
            telemetry=telemetry,
        )
    except Exception as exc:  # noqa: BLE001 — rerank must never break retrieval
        logger.warning("cross_encoder_llm_failed", error=str(exc))
        return documents

    scores = _parse_scores(raw, len(candidates))
    if not scores:
        logger.debug("cross_encoder_no_scores", raw_preview=raw[:120])
        return documents

    # Stable sort: by score desc, original index as tiebreak. Unscored → _UNSCORED
    # so they retain their retrieval order beneath everything the model ranked.
    order = sorted(
        range(len(candidates)),
        key=lambda i: (-scores.get(i, _UNSCORED), i),
    )
    reranked = []
    for i in order:
        doc = dict(candidates[i])
        if i in scores:
            doc["rerank_score"] = round(scores[i], 2)
        reranked.append(doc)

    logger.info(
        "cross_encoder_reranked",
        candidates=len(candidates),
        scored=len(scores),
        moved_top=(order[0] != 0),
    )
    return reranked + tail


def _parse_scores(raw: str, count: int) -> dict[int, float]:
    """Parse the model's JSON into ``{candidate_index: score}``.

    Defensive: tolerates code fences and stray prose, ignores out-of-range or
    duplicate ids (first wins), clamps scores to [0, 10]. Returns an empty dict
    on anything it can't trust — the caller treats that as "keep input order".
    """
    if not raw:
        return {}
    text = raw.strip()
    # Strip ```json fences if the model wrapped its output.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Last resort: pull the first {...} object out of surrounding prose.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return {}

    entries = data.get("scores") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {}

    out: dict[int, float] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry["id"])
            score = float(entry["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= idx < count and idx not in out:
            out[idx] = max(0.0, min(10.0, score))
    return out
