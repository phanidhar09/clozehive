"""PostHog analytics — LLM generation capture + graceful lifecycle.

Entirely optional and defensive, mirroring the pattern used for Prometheus and
Sentry: a no-op unless ``POSTHOG_API_KEY`` is set *and* the ``posthog`` SDK is
installed. Nothing here ever raises into the request path.

Events use PostHog's native **LLM Analytics** schema (``$ai_generation`` with
``$ai_*`` properties) so generations show up in the LLM Analytics product with no
extra dashboard wiring. We deliberately do **not** send prompt/response *content*
(``$ai_input`` / ``$ai_output_choices``) — only metadata (model, tokens, cost,
latency, tier) — so no user wardrobe data leaves the backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("analytics")
settings = get_settings()

_client: Any = None
_ENABLED = False

try:
    from posthog import Posthog

    _POSTHOG_AVAILABLE = True
except ImportError:  # pragma: no cover
    _POSTHOG_AVAILABLE = False


def init_analytics() -> None:
    """Initialise the PostHog client. Safe to call once at startup; idempotent."""
    global _client, _ENABLED
    if _ENABLED:
        return
    if not settings.posthog_api_key:
        logger.info("posthog_not_configured", msg="POSTHOG_API_KEY unset — LLM analytics disabled")
        return
    if not _POSTHOG_AVAILABLE:
        logger.warning("posthog_unavailable", reason="posthog sdk not installed")
        return
    try:
        _client = Posthog(
            project_api_key=settings.posthog_api_key,
            host=settings.posthog_host,
            # Background flushing keeps the request path free of network I/O.
            flush_interval=5.0,
            # Never let analytics raise into application code.
            on_error=lambda err, items: logger.debug("posthog_flush_error", error=str(err)),
        )
        _ENABLED = True
        logger.info("posthog_initialized", host=settings.posthog_host)
    except Exception as exc:  # pragma: no cover
        logger.warning("posthog_init_failed", error=str(exc))


def shutdown_analytics() -> None:
    """Flush and close the PostHog client on shutdown."""
    global _client, _ENABLED
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:  # pragma: no cover
            pass
    _client = None
    _ENABLED = False


@dataclass
class LLMTelemetry:
    """Call-site context the raw LLM client does not know on its own.

    Assembled by the pipeline (which knows the user, routing decision, and
    operation) and threaded down to the generation-capture point.
    """

    operation: str = "stylist_chat"
    user_id: str | None = None
    trace_id: str | None = None
    tier: str | None = None
    route_reasons: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def capture_llm_generation(
    *,
    model: str,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    input_cost_usd: float,
    output_cost_usd: float,
    latency_seconds: float,
    token_source: str,
    telemetry: LLMTelemetry | None = None,
    is_error: bool = False,
) -> None:
    """Emit a PostHog ``$ai_generation`` event. No-op when analytics is disabled."""
    if not _ENABLED or _client is None:
        return
    t = telemetry or LLMTelemetry()
    try:
        distinct_id = t.user_id or "system"
        properties: dict[str, Any] = {
            "$ai_provider": provider,
            "$ai_model": model,
            "$ai_input_tokens": prompt_tokens,
            "$ai_output_tokens": completion_tokens,
            "$ai_input_cost_usd": round(input_cost_usd, 6),
            "$ai_output_cost_usd": round(output_cost_usd, 6),
            "$ai_total_cost_usd": round(input_cost_usd + output_cost_usd, 6),
            "$ai_latency": round(latency_seconds, 3),
            "$ai_trace_id": t.trace_id or t.user_id or "anonymous",
            "$ai_is_error": is_error,
            "$ai_http_status": 500 if is_error else 200,
            # Custom dimensions for slicing cost/latency in PostHog.
            "operation": t.operation,
            "tier": t.tier,
            "route_reasons": t.route_reasons,
            "token_source": token_source,  # "api" (exact) | "estimated" (fallback)
            "environment": settings.environment,
            **t.extra,
        }
        _client.capture(distinct_id=distinct_id, event="$ai_generation", properties=properties)
    except Exception as exc:  # pragma: no cover
        logger.debug("posthog_capture_failed", error=str(exc))
