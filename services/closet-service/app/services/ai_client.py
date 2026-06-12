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


def _enrich_agent_packing_for_trips(data: dict[str, Any]) -> dict[str, Any]:
    """
    MCP packing JSON is a PackingResult (packing_list, missing_items, …).
    Trip routes expect take_from_your_closet / you_might_still_need like packing_service.
    """
    if not data.get("take_from_your_closet"):
        take: list[dict[str, Any]] = []
        for it in data.get("packing_list") or []:
            if not isinstance(it, dict) or not it.get("available_in_closet"):
                continue
            take.append({
                "item_id": it.get("closet_item_id"),
                "name": str(it.get("name") or ""),
                "category": str(it.get("category") or "general"),
                "reason": str(it.get("reason") or "Recommended for this trip."),
                "recommended_days": [],
            })
        data["take_from_your_closet"] = take

    if not data.get("you_might_still_need"):
        need: list[dict[str, Any]] = []
        for it in data.get("missing_items") or []:
            if not isinstance(it, dict):
                continue
            need.append({
                "name": str(it.get("name") or ""),
                "category": str(it.get("category") or "general"),
                "reason": str(it.get("reason") or "Consider bringing this."),
            })
        data["you_might_still_need"] = need

    if data.get("packing_list") is not None and data.get("items") is None:
        data["items"] = data["packing_list"]

    return data


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
    notes: str | None = None,
    user_style_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "purpose": purpose,
        "notes": notes,
        "closet_items": closet_items,
        "user_style_profile": user_style_profile,
    }
    try:
        resp = await get_client().post("/api/v1/agent/packing", json=payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        # Enrich for frontend TravelPlanner (expects duration_days + trip_type).
        if isinstance(data, dict):
            _enrich_agent_packing_for_trips(data)
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
