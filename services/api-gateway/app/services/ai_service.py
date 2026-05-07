"""OpenAI chat service for ClozeHive stylist responses (streaming and full reply)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from openai import APIError, AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("ai_service")

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
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


def _chat_messages(system_prompt: str, messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"role": "system", "content": system_prompt}, *_normalise_messages(messages)]


async def stream_chat(messages: list[dict[str, Any]], system_prompt: str) -> AsyncIterator[str]:
    """Yield OpenAI response text chunks for SSE streaming."""
    if not settings.openai_api_key:
        yield "OpenAI API key is not configured. Please set OPENAI_API_KEY."
        return

    try:
        stream = await _get_client().chat.completions.create(
            model=settings.openai_model,
            max_tokens=settings.openai_max_tokens,
            messages=_chat_messages(system_prompt, messages),
            stream=True,
        )
        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice and choice.delta and choice.delta.content:
                yield choice.delta.content
    except APIError as exc:
        logger.error("openai_chat_error", error=str(exc))
        yield "The AI stylist is temporarily unavailable. Please try again shortly."


async def chat(messages: list[dict[str, Any]], system_prompt: str) -> str:
    """Return a complete model response while preserving the streaming implementation."""
    parts: list[str] = []
    async for chunk in stream_chat(messages, system_prompt):
        parts.append(chunk)
    return "".join(parts)
