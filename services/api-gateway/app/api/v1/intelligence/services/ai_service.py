"""OpenAI chat service for ClozeHive stylist responses (streaming and full reply)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langsmith import traceable
from openai import APIError, RateLimitError

from app.core.config import get_settings
from app.core.logging import get_logger
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


async def stream_chat(
    messages: list[dict[str, Any]],
    system_prompt: str,
    *,
    use_json_mode: bool = False,
    max_tokens: int | None = None,
    temperature: float = 0.7,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Yield OpenAI response text chunks for SSE streaming.

    Args:
        use_json_mode: When True, sets response_format to json_object. The system
            prompt MUST contain the word "json" for this to work (OpenAI requirement).
        max_tokens: Override the default token budget from settings.
        temperature: Sampling temperature (0=deterministic, 1=creative).
        model: Override the model. Defaults to ``settings.openai_model``; the
            model router (``model_router.py``) supplies this per turn.
    """
    if not settings.openai_api_key:
        yield "OpenAI API key is not configured. Please set OPENAI_API_KEY."
        return

    request_params: dict[str, Any] = {
        "model": model or settings.openai_model,
        "max_tokens": max_tokens or settings.openai_max_tokens,
        "temperature": temperature,
        "messages": _chat_messages(system_prompt, messages),
        "stream": True,
    }
    if use_json_mode:
        request_params["response_format"] = {"type": "json_object"}

    for attempt in range(_MAX_RETRIES + 1):
        try:
            stream = await _get_client().chat.completions.create(**request_params)
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if choice and choice.delta and choice.delta.content:
                    yield choice.delta.content
            return
        except RateLimitError as exc:
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning("openai_rate_limited_retry", attempt=attempt + 1, delay=delay)
                await asyncio.sleep(delay)
                continue
            logger.error("openai_rate_limit_exhausted", error=str(exc))
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
) -> str:
    """Return a complete model response, collecting all streaming chunks.

    Args:
        use_json_mode: When True, enforces JSON output via response_format.
            The system prompt must contain the word "json".
        max_tokens: Override the default token budget.
        temperature: Sampling temperature.
        model: Override the model (supplied per turn by the model router).
    """
    parts: list[str] = []
    async for chunk in stream_chat(
        messages,
        system_prompt,
        use_json_mode=use_json_mode,
        max_tokens=max_tokens,
        temperature=temperature,
        model=model,
    ):
        parts.append(chunk)
    return "".join(parts)
