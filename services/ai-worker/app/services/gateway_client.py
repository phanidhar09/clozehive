"""HTTP client for calling back into the api-gateway's internal endpoints.

Used by the durable embedding task: the gateway owns the embedding/OpenAI code,
so the worker triggers regeneration via the token-protected internal endpoint
rather than duplicating that logic here.
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings

settings = get_settings()
_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.gateway_internal_url,
            timeout=httpx.Timeout(settings.http_timeout_seconds, read=None),
            headers={"X-Internal-Token": settings.internal_service_token},
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    reraise=True,
)
async def regenerate_embedding(item_id: str) -> None:
    response = await client().post(f"/internal/embeddings/{item_id}")
    response.raise_for_status()
