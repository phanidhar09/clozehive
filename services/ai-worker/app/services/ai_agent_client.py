"""HTTP client for the AI agent service."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings

settings = get_settings()
_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.ai_agent_url,
            timeout=httpx.Timeout(settings.http_timeout_seconds, read=None),
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _retryable(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        reraise=True,
    )(func)


@_retryable
async def analyze_image(file_path: str, media_type: str) -> dict[str, Any]:
    image_b64 = base64.b64encode(Path(file_path).read_bytes()).decode("utf-8")
    response = await client().post(
        "/api/v1/agent/vision/analyze",
        json={"image_base64": image_b64, "media_type": media_type},
    )
    response.raise_for_status()
    return response.json()


@_retryable
async def generate_outfit(payload: dict[str, Any]) -> dict[str, Any]:
    response = await client().post("/api/v1/agent/outfit", json=payload)
    response.raise_for_status()
    return response.json()


@_retryable
async def generate_packing(payload: dict[str, Any]) -> dict[str, Any]:
    response = await client().post("/api/v1/agent/packing", json=payload)
    response.raise_for_status()
    return response.json()


async def stream_chat(payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    async with client().stream("POST", "/api/v1/agent/chat/stream", json=payload) as response:
        response.raise_for_status()
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            parts = buffer.split("\n\n")
            buffer = parts.pop() or ""
            for part in parts:
                for line in part.splitlines():
                    if line.startswith("data: "):
                        yield json.loads(line[6:])
