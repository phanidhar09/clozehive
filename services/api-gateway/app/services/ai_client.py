"""
AI Agent HTTP client — talks to the ai-agent service.
Handles timeouts, retries, and serialization so routes stay thin.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings
from app.core.exceptions import AIServiceError, ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger("ai_client")
settings = get_settings()

# ── Shared async HTTP client (lifecycle managed in main.py) ──────────────────

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.ai_agent_url,
            timeout=httpx.Timeout(settings.ai_timeout_seconds),
            headers={"Content-Type": "application/json"},
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None


# ── Retry decorator ───────────────────────────────────────────────────────────

def _retryable(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )(func)


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
        resp = await get_client().post("/api/v1/agent/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["reply"]
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
) -> dict[str, Any]:
    payload = {
        "closet_items": closet_items,
        "occasion": occasion,
        "weather": weather,
        "temperature": temperature,
    }
    try:
        resp = await get_client().post("/api/v1/agent/outfit", json=payload)
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        raise ServiceUnavailableError("AI service timed out")
    except httpx.HTTPStatusError as exc:
        raise AIServiceError("Outfit generation failed", detail=exc.response.text)


@_retryable
async def generate_packing_list(
    destination: str,
    start_date: str,
    end_date: str,
    purpose: str,
    closet_items: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "purpose": purpose,
        "closet_items": closet_items,
    }
    try:
        resp = await get_client().post("/api/v1/agent/packing", json=payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        # Enrich for frontend TravelPlanner (expects duration_days + trip_type).
        if isinstance(data, dict):
            try:
                s = date.fromisoformat(start_date)
                e = date.fromisoformat(end_date)
                data.setdefault("duration_days", max(1, (e - s).days + 1))
            except ValueError:
                data.setdefault("duration_days", 1)
            data.setdefault("trip_type", purpose)
            # Normalise daily_plan entries for UI that reads outfit_suggestion / items_needed.
            for day in data.get("daily_plan") or []:
                if isinstance(day, dict):
                    if day.get("outfit_suggestion") is None and day.get("outfit_name"):
                        day["outfit_suggestion"] = day["outfit_name"]
                    if day.get("items_needed") is None and day.get("items"):
                        day["items_needed"] = day["items"]
        return data
    except httpx.TimeoutException:
        raise ServiceUnavailableError("AI service timed out")
    except httpx.HTTPStatusError as exc:
        raise AIServiceError("Packing list generation failed", detail=exc.response.text)


@_retryable
async def analyze_image(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {"image_base64": image_b64, "media_type": media_type}
    try:
        resp = await get_client().post("/api/v1/agent/vision/analyze", json=payload)
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        raise ServiceUnavailableError("Vision analysis timed out")
    except httpx.HTTPStatusError as exc:
        raise AIServiceError("Vision analysis failed", detail=exc.response.text)
