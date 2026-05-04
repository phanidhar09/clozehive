"""Direct Anthropic chat service for ClosetIQ stylist responses."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("ai_service")

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _normalise_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalised: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        if content.strip():
            normalised.append({"role": role, "content": content})
    return normalised


async def stream_chat(messages: list[dict[str, Any]], system_prompt: str) -> AsyncIterator[str]:
    """Yield Claude response text chunks for SSE streaming."""
    if not settings.anthropic_api_key:
        yield "Anthropic API key is not configured. Please set ANTHROPIC_API_KEY."
        return

    try:
        async with _get_client().messages.stream(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=system_prompt,
            messages=_normalise_messages(messages),
        ) as stream:
            async for chunk in stream.text_stream:
                if chunk:
                    yield chunk
    except anthropic.APIError as exc:
        logger.error("anthropic_api_error", error=str(exc))
        yield "The AI stylist is temporarily unavailable. Please try again shortly."


async def chat(messages: list[dict[str, Any]], system_prompt: str) -> str:
    """Return a complete Claude response while preserving the streaming implementation."""
    parts: list[str] = []
    async for chunk in stream_chat(messages, system_prompt):
        parts.append(chunk)
    return "".join(parts)
