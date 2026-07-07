"""OpenAI chat service for ClozeHive stylist responses (streaming and full reply)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from langsmith import traceable
from openai import APIError, RateLimitError

from app.core.analytics import LLMTelemetry, capture_llm_generation
from app.core.config import get_settings
from app.core.llm_pricing import cost_usd
from app.core.logging import get_logger
from app.core.metrics import record_ai_cost, record_ai_tokens
from app.core.openai_tracing import make_openai_client, wrap_openai_client

settings = get_settings()
logger = get_logger("ai_service")

_client = None

# Maximum retries for transient OpenAI errors (rate limits, 5xx)
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 1.0  # seconds, doubles each attempt


def _get_client():
    global _client
    if _client is None:
        _client = wrap_openai_client(
            make_openai_client(settings.openai_api_key, base_url=settings.openai_api_base_url),
        )
    return _client


def _normalise_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalised: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            # Vision message — pass through as-is (OpenAI multimodal content array)
            if content:
                normalised.append({"role": role, "content": content})
        else:
            if not isinstance(content, str):
                content = str(content)
            if content.strip():
                normalised.append({"role": role, "content": content})
    return normalised


def _chat_messages(system_prompt: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"role": "system", "content": system_prompt}, *_normalise_messages(messages)]


def _estimate_tokens_from_messages(messages: list[dict[str, Any]]) -> int:
    """Rough prompt-token estimate (~4 chars/token) for the no-usage fallback."""
    chars = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    chars += len(str(block.get("text", "")))
                else:
                    chars += 800  # image block — rough fixed proxy for its token cost
    return max(1, chars // 4)


def _record_generation(
    *,
    model: str,
    messages: list[dict[str, Any]],
    output_chars: int,
    usage: Any,
    elapsed: float,
    telemetry: LLMTelemetry | None,
    is_error: bool = False,
    provider: str = "openai",
) -> None:
    """Record token/cost metrics (Prometheus) and emit a PostHog $ai_generation event.

    Uses exact ``usage`` from the API when available (``stream_options.include_usage``);
    otherwise falls back to a char-based estimate so dashboards stay populated even
    behind a proxy that strips usage. Never raises into the request path.
    """
    try:
        if usage is not None:
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            token_source = "api"
        else:
            prompt_tokens = _estimate_tokens_from_messages(messages)
            completion_tokens = max(0, output_chars // 4)
            token_source = "estimated"

        input_cost, output_cost, _ = cost_usd(model, prompt_tokens, completion_tokens)
        record_ai_tokens(model, prompt=prompt_tokens, completion=completion_tokens)
        record_ai_cost(model, input_cost + output_cost)
        capture_llm_generation(
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            latency_seconds=elapsed,
            token_source=token_source,
            telemetry=telemetry,
            is_error=is_error,
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break generation
        logger.debug("record_generation_failed", error=str(exc))


async def stream_chat(
    messages: list[dict[str, Any]],
    system_prompt: str,
    *,
    use_json_mode: bool = False,
    max_tokens: int | None = None,
    temperature: float = 0.7,
    model: str | None = None,
    telemetry: LLMTelemetry | None = None,
) -> AsyncIterator[str]:
    """Yield OpenAI response text chunks for SSE streaming.

    Args:
        use_json_mode: When True, sets response_format to json_object. The system
            prompt MUST contain the word "json" for this to work (OpenAI requirement).
        max_tokens: Override the default token budget from settings.
        temperature: Sampling temperature (0=deterministic, 1=creative).
        model: Override the model. Defaults to ``settings.openai_model``; the
            model router (``model_router.py``) supplies this per turn.
        telemetry: Optional call-site context (user, tier, trace, operation) used
            to tag the token/cost capture. Capture happens regardless; this only
            enriches the dimensions.
    """
    resolved_model = model or settings.openai_model
    if not settings.openai_api_key:
        yield "OpenAI API key is not configured. Please set OPENAI_API_KEY."
        return

    request_params: dict[str, Any] = {
        "model": resolved_model,
        "max_tokens": max_tokens or settings.openai_max_tokens,
        "temperature": temperature,
        "messages": _chat_messages(system_prompt, messages),
        "stream": True,
        # Ask the API to append a final usage-only chunk (empty choices) so we can
        # record exact token counts even on the streaming path.
        "stream_options": {"include_usage": True},
    }
    if use_json_mode:
        request_params["response_format"] = {"type": "json_object"}

    start = time.perf_counter()
    for attempt in range(_MAX_RETRIES + 1):
        usage: Any = None
        output_chars = 0
        try:
            stream = await _get_client().chat.completions.create(**request_params)
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                choice = chunk.choices[0] if chunk.choices else None
                if choice and choice.delta and choice.delta.content:
                    output_chars += len(choice.delta.content)
                    yield choice.delta.content
            _record_generation(
                model=resolved_model,
                messages=request_params["messages"],
                output_chars=output_chars,
                usage=usage,
                elapsed=time.perf_counter() - start,
                telemetry=telemetry,
            )
            return
        except RateLimitError as exc:
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning("openai_rate_limited_retry", attempt=attempt + 1, delay=delay)
                await asyncio.sleep(delay)
                continue
            logger.error("openai_rate_limit_exhausted", error=str(exc))
            _record_generation(
                model=resolved_model,
                messages=request_params["messages"],
                output_chars=0,
                usage=None,
                elapsed=time.perf_counter() - start,
                telemetry=telemetry,
                is_error=True,
            )
            yield "The AI stylist is temporarily unavailable due to high demand. Please try again in a moment."
            return
        except APIError as exc:
            if attempt < _MAX_RETRIES and getattr(exc, "status_code", 0) >= 500:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "openai_server_error_retry",
                    attempt=attempt + 1,
                    delay=delay,
                    status=getattr(exc, "status_code", None),
                )
                await asyncio.sleep(delay)
                continue
            logger.error("openai_chat_error", error=str(exc), status=getattr(exc, "status_code", None))
            _record_generation(
                model=resolved_model,
                messages=request_params["messages"],
                output_chars=0,
                usage=None,
                elapsed=time.perf_counter() - start,
                telemetry=telemetry,
                is_error=True,
            )
            yield "The AI stylist is temporarily unavailable. Please try again shortly."
            return


@traceable(name="gateway_openai_stylist_chat", run_type="chain")
async def chat(
    messages: list[dict[str, Any]],
    system_prompt: str,
    *,
    use_json_mode: bool = False,
    max_tokens: int | None = None,
    temperature: float = 0.7,
    model: str | None = None,
    telemetry: LLMTelemetry | None = None,
) -> str:
    """Return a complete model response, collecting all streaming chunks.

    Args:
        use_json_mode: When True, enforces JSON output via response_format.
            The system prompt must contain the word "json".
        max_tokens: Override the default token budget.
        temperature: Sampling temperature.
        model: Override the model (supplied per turn by the model router).
        telemetry: Optional call-site context for token/cost capture.
    """
    parts: list[str] = []
    async for chunk in stream_chat(
        messages,
        system_prompt,
        use_json_mode=use_json_mode,
        max_tokens=max_tokens,
        temperature=temperature,
        model=model,
        telemetry=telemetry,
    ):
        parts.append(chunk)
    return "".join(parts)
