"""Langfuse (self-hosted, v2) tracing + evaluation scoring.

A thin, entirely optional wrapper — a no-op unless ``LANGFUSE_PUBLIC_KEY`` /
``LANGFUSE_SECRET_KEY`` are set *and* the ``langfuse`` SDK is installed. Mirrors
the defensive contract of :mod:`app.core.analytics`: nothing here ever raises
into the request path, and the SDK's own background flushing keeps request
handlers free of network I/O.

Two responsibilities:

- :func:`record_generation` — emit a trace + generation observation per LLM turn
  (model, tier, tokens, cost, latency), so every production interaction shows up
  in the Langfuse dashboard for live monitoring.
- :func:`record_scores` — attach evaluation scores (e.g. the deterministic
  groundedness / hallucination signals ``claim_grounding`` and
  ``ai_output_validator`` already compute) to a trace, so quality is tracked
  alongside cost/latency.

Self-hosted, so unlike the PostHog path this *may* capture prompt/response
content — but only when ``LANGFUSE_CAPTURE_CONTENT`` is explicitly enabled.
Default is metadata-only, matching the app's existing privacy stance.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("langfuse")
settings = get_settings()

_client: Any = None
_ENABLED = False

try:
    from langfuse import Langfuse

    _LANGFUSE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _LANGFUSE_AVAILABLE = False


def _capture_content() -> bool:
    return os.getenv("LANGFUSE_CAPTURE_CONTENT", "").strip().lower() in {"1", "true", "yes", "on"}


def init_langfuse() -> None:
    """Initialise the Langfuse client. Safe to call once at startup; idempotent."""
    global _client, _ENABLED
    if _ENABLED:
        return
    public_key = getattr(settings, "langfuse_public_key", "")
    secret_key = getattr(settings, "langfuse_secret_key", "")
    if not public_key or not secret_key:
        logger.info("langfuse_not_configured", msg="LANGFUSE_*_KEY unset — Langfuse tracing disabled")
        return
    if not _LANGFUSE_AVAILABLE:
        logger.warning("langfuse_unavailable", reason="langfuse sdk not installed")
        return
    try:
        _client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=getattr(settings, "langfuse_host", "") or "http://localhost:3100",
        )
        _ENABLED = True
        logger.info("langfuse_initialized", host=settings.langfuse_host)
    except Exception as exc:  # pragma: no cover
        logger.warning("langfuse_init_failed", error=str(exc))


def shutdown_langfuse() -> None:
    """Flush and close the Langfuse client on shutdown."""
    global _client, _ENABLED
    if _client is not None:
        try:
            _client.flush()
            _client.shutdown()
        except Exception:  # pragma: no cover
            pass
    _client = None
    _ENABLED = False


def record_generation(
    *,
    trace_id: str | None,
    model: str,
    provider: str,
    operation: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_cost_usd: float,
    latency_seconds: float,
    tier: str | None = None,
    user_id: str | None = None,
    is_error: bool = False,
    input_text: str | None = None,
    output_text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Emit a trace + generation observation for one LLM turn.

    Returns the trace id (so scores can be attached to it), or ``None`` when
    Langfuse is disabled. Never raises.
    """
    if not _ENABLED or _client is None:
        return None
    try:
        trace = _client.trace(
            id=trace_id or None,
            name=operation,
            user_id=user_id,
            tags=[f"tier:{tier}"] if tier else None,
            metadata={"provider": provider, "tier": tier, "environment": settings.environment, **(metadata or {})},
        )
        capture = _capture_content()
        trace.generation(
            name=operation,
            model=model,
            usage={
                "input": prompt_tokens,
                "output": completion_tokens,
                "total": prompt_tokens + completion_tokens,
                "unit": "TOKENS",
                "input_cost": None,
                "output_cost": None,
                "total_cost": round(total_cost_usd, 6),
            },
            input=(input_text if capture else None),
            output=(output_text if capture else None),
            level="ERROR" if is_error else "DEFAULT",
            metadata={"latency_seconds": round(latency_seconds, 3), "provider": provider},
        )
        return trace.id
    except Exception as exc:  # noqa: BLE001 — tracing must never break generation
        logger.debug("langfuse_generation_failed", error=str(exc))
        return None


def record_retrieval(
    *,
    query: str,
    doc_count: int,
    top_relevance: float,
    latency_seconds: float,
    user_id: str | None = None,
    operation: str = "fashion_knowledge_search",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a retrieval trace + a ``retrieval_top_relevance`` score for a RAG
    search, so retrieval quality trends live alongside generation. No-op when
    disabled. Never raises.
    """
    if not _ENABLED or _client is None:
        return
    try:
        trace = _client.trace(
            name=operation,
            user_id=user_id,
            input=(query if _capture_content() else None),
            metadata={
                "doc_count": doc_count,
                "latency_seconds": round(latency_seconds, 3),
                "environment": settings.environment,
                **(metadata or {}),
            },
        )
        _client.score(trace_id=trace.id, name="retrieval_top_relevance", value=float(top_relevance))
        _client.score(trace_id=trace.id, name="retrieval_doc_count", value=float(doc_count))
    except Exception as exc:  # noqa: BLE001
        logger.debug("langfuse_retrieval_failed", error=str(exc))


def record_scores(trace_id: str, scores: dict[str, float], *, comment: str | None = None) -> None:
    """Attach one or more numeric evaluation scores (0-1) to a trace. No-op when
    disabled. Feed it the deterministic signals the app already computes.
    """
    if not _ENABLED or _client is None or not trace_id:
        return
    try:
        for name, value in scores.items():
            _client.score(trace_id=trace_id, name=name, value=float(value), comment=comment)
    except Exception as exc:  # noqa: BLE001
        logger.debug("langfuse_score_failed", error=str(exc))
