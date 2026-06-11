"""Web intelligence — single cached Tavily wrapper (Phase 1 of the roadmap).

Every feature that needs live web knowledge (destination dress guidelines,
festival discovery, venue/airline rules, trend grounding) routes through this
one module. Nothing else in the codebase may call Tavily directly — that keeps
caching, cost control, and failure behaviour in one place.

Contract:
- ``cached_search`` returns a small, prompt-friendly dict
  ``{"answer": str, "sources": [{"title", "url"}], "fetched_at": iso}``
  or ``None`` when the layer is unavailable (no API key, network failure,
  empty answer). Callers MUST treat None as "feature off" and fall back to
  their static/LLM-infer behaviour — web intelligence is enhancement, never
  a hard dependency.
- Results are cached in Redis under ``webintel:<namespace>:<key>`` for the
  caller-supplied TTL; repeated failures are negative-cached briefly so a
  Tavily outage can't add per-request latency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core import cache_service
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("web_intelligence")

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_REQUEST_TIMEOUT_S = 12
_MAX_SOURCES = 3
# Negative-cache window after a failed fetch — protects request latency during
# a Tavily outage without hiding it for long.
_FAILURE_TTL_S = 15 * 60
_FAILURE_MARKER = {"__failed__": True}


def is_enabled() -> bool:
    """True when a Tavily API key is configured."""
    return bool(get_settings().tavily_api_key)


def _cache_key(namespace: str, key: str) -> str:
    return cache_service.namespaced_key("webintel", namespace, key.strip().lower())


async def _tavily_search(query: str, *, max_results: int) -> dict[str, Any] | None:
    """One raw Tavily call → normalized payload, or None on any failure."""
    settings = get_settings()
    if not settings.tavily_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
            resp = await client.post(
                _TAVILY_SEARCH_URL,
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": True,
                    "max_results": max_results,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 — any failure means "layer off"
        logger.warning("tavily_search_failed", error=str(exc), query=query[:80])
        return None

    answer = (data.get("answer") or "").strip()
    if not answer:
        logger.info("tavily_empty_answer", query=query[:80])
        return None

    sources = [
        {"title": (r.get("title") or "")[:120], "url": r.get("url") or ""}
        for r in (data.get("results") or [])[:_MAX_SOURCES]
        if r.get("url")
    ]
    return {
        "answer": answer,
        "sources": sources,
        "fetched_at": datetime.now(UTC).isoformat(),
    }


async def cached_search(
    query: str,
    *,
    namespace: str,
    key: str,
    ttl_seconds: int,
    max_results: int = 5,
) -> dict[str, Any] | None:
    """Cache-through Tavily answer search.

    ``namespace`` groups a feature's entries (e.g. "dress-guidelines");
    ``key`` identifies the entity (e.g. a normalized destination). The same
    key is shared across all users, so one fetch benefits everyone.
    """
    if not is_enabled():
        return None

    ck = _cache_key(namespace, key)
    try:
        cached = await cache_service.get(ck)
    except Exception as exc:  # noqa: BLE001 — cache problems must not break the request
        logger.warning("webintel_cache_get_failed", error=str(exc))
        cached = None
    if cached is not None:
        if cached == _FAILURE_MARKER:
            return None
        return cached

    result = await _tavily_search(query, max_results=max_results)

    try:
        if result is not None:
            await cache_service.set(ck, result, ttl_seconds)
        else:
            await cache_service.set(ck, _FAILURE_MARKER, _FAILURE_TTL_S)
    except Exception as exc:  # noqa: BLE001
        logger.warning("webintel_cache_set_failed", error=str(exc))

    if result is not None:
        logger.info("webintel_fetched", namespace=namespace, key=key[:60])
    return result


def format_sources_line(result: dict[str, Any]) -> str:
    """One compact 'Sources: …' line for prompt blocks. "" when none."""
    sources = result.get("sources") or []
    if not sources:
        return ""
    titles = ", ".join(s["title"] or s["url"] for s in sources)
    return f"Sources: {titles}"
