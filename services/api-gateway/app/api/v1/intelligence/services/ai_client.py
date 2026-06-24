"""
AI Agent HTTP client — talks to the ai-agent service.
Handles timeouts, retries, and serialization so routes stay thin.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.circuit_breaker import CircuitOpenError, ai_agent_breaker
from app.core.config import get_settings
from app.core.exceptions import AIServiceError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.metrics import track_ai

logger = get_logger("ai_client")
settings = get_settings()


# ── Shared async HTTP client (lifecycle managed in main.py) ──────────────────

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.ai_agent_url,
            # connect timeout is short so an absent ai-agent fails fast;
            # read timeout is the full budget for an active response.
            timeout=httpx.Timeout(
                connect=5.0,
                read=float(settings.ai_timeout_seconds),
                write=10.0,
                pool=5.0,
            ),
            headers={
                "Content-Type": "application/json",
                **({"X-Internal-Token": settings.internal_service_token} if settings.internal_service_token else {}),
            },
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None


# ── Retry decorator ───────────────────────────────────────────────────────────


def _retryable(func):
    # Retry only on NetworkError (connection refused / reset) — NOT on TimeoutException.
    # TimeoutException means the server IS reachable but slow; retrying wastes budget.
    # Cap at 2 attempts so a down ai-agent never burns more than ~10 s before fallback.
    return retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(httpx.NetworkError),
        reraise=True,
    )(func)


# ── Circuit-breaker-wrapped request ───────────────────────────────────────────


async def _agent_request(request_factory):
    """Run an ai-agent HTTP call through the circuit breaker.

    Only transport errors, timeouts, and 5xx count as breaker failures (a down
    or overloaded dependency). 4xx responses are a healthy round-trip — they pass
    through the breaker and are raised by the caller's ``raise_for_status``, so a
    burst of client errors never trips the breaker.
    """

    async def _do():
        resp = await request_factory()
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    return await ai_agent_breaker.call(_do)


# ── API calls ─────────────────────────────────────────────────────────────────


@_retryable
async def chat(
    message: str,
    history: list[dict[str, str]] | None = None,
    closet_items: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
) -> str:
    """Send a chat message to the wardrobe agent and return reply text."""
    payload = {
        "message": message,
        "history": history or [],
        "closet_items": closet_items or [],
        "user_id": user_id,
    }
    try:
        with track_ai("chat"):
            resp = await _agent_request(lambda: get_client().post("/api/v1/agent/chat", json=payload))
            resp.raise_for_status()
            return resp.json()["reply"]
    except CircuitOpenError:
        raise ServiceUnavailableError("AI service is temporarily unavailable")
    except httpx.TimeoutException:
        raise ServiceUnavailableError("AI service timed out — please try again")
    except httpx.HTTPStatusError as exc:
        raise AIServiceError(f"AI service returned {exc.response.status_code}")
    except httpx.TransportError as exc:
        raise ServiceUnavailableError("AI service is unreachable", detail=str(exc))


async def stream_chat(
    message: str,
    history: list[dict[str, str]] | None = None,
    closet_items: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Proxy true SSE events from ai-agent without buffering the full answer."""
    payload = {
        "message": message,
        "history": history or [],
        "closet_items": closet_items or [],
        "user_id": user_id,
    }

    try:
        async with get_client().stream(
            "POST",
            "/api/v1/agent/chat/stream",
            json=payload,
            timeout=httpx.Timeout(settings.ai_timeout_seconds, read=None),
        ) as resp:
            resp.raise_for_status()
            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                parts = buffer.split("\n\n")
                buffer = parts.pop() or ""
                for part in parts:
                    for line in part.splitlines():
                        if not line.startswith("data: "):
                            continue
                        try:
                            event = json.loads(line[6:])
                        except json.JSONDecodeError:
                            logger.warning("ai_stream_malformed_event", raw=line[:200])
                            continue
                        if isinstance(event, dict):
                            yield event
    except httpx.TimeoutException:
        raise ServiceUnavailableError("AI service timed out — please try again")
    except httpx.HTTPStatusError as exc:
        raise AIServiceError(f"AI service returned {exc.response.status_code}", detail=exc.response.text)
    except httpx.TransportError as exc:
        raise ServiceUnavailableError("AI service is unreachable", detail=str(exc))


@_retryable
async def generate_outfits(
    closet_items: list[dict[str, Any]],
    occasion: str,
    weather: str,
    temperature: float,
    user_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "closet_items": closet_items,
        "occasion": occasion,
        "weather": weather,
        "temperature": temperature,
        "user_profile": user_profile,
    }
    try:
        with track_ai("generate_outfits"):
            resp = await _agent_request(lambda: get_client().post("/api/v1/agent/outfit", json=payload))
            resp.raise_for_status()
            return resp.json()
    except CircuitOpenError:
        raise ServiceUnavailableError("AI service is temporarily unavailable")
    except httpx.TimeoutException:
        raise ServiceUnavailableError("AI service timed out")
    except httpx.HTTPStatusError as exc:
        raise AIServiceError("Outfit generation failed", detail=exc.response.text)


@_retryable
async def analyze_image(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {"image_base64": image_b64, "media_type": media_type}
    try:
        with track_ai("analyze_image"):
            resp = await _agent_request(lambda: get_client().post("/api/v1/agent/vision/analyze", json=payload))
            resp.raise_for_status()
            return resp.json()
    except CircuitOpenError:
        raise ServiceUnavailableError("AI service is temporarily unavailable")
    except httpx.TimeoutException:
        raise ServiceUnavailableError("Vision analysis timed out")
    except httpx.HTTPStatusError as exc:
        raise AIServiceError("Vision analysis failed", detail=exc.response.text)
