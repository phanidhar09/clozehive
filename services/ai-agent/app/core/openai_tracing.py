"""LangSmith instrumentation for OpenAI SDK clients (ai-agent)."""

from __future__ import annotations

import os

from openai import AsyncOpenAI


def langsmith_tracing_enabled() -> bool:
    if os.getenv("LANGSMITH_TRACING", "").lower() not in ("1", "true", "yes"):
        if os.getenv("LANGCHAIN_TRACING_V2", "").lower() not in ("1", "true", "yes"):
            return False
    key = (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or "").strip()
    return bool(key)


def make_openai_client(api_key: str, *, base_url: str) -> AsyncOpenAI:
    """Create an AsyncOpenAI client.

    ``base_url`` must always be supplied (typically from Settings). Passing it explicitly
    prevents the SDK from reading ``OPENAI_BASE_URL`` from the environment and redirecting
    traffic to misconfigured OpenAI-compatible proxies.
    """
    root = base_url.strip() if base_url else ""
    resolved = root or "https://api.openai.com/v1"
    return AsyncOpenAI(api_key=api_key or "no-key", base_url=resolved)


def wrap_openai_client(client: AsyncOpenAI) -> AsyncOpenAI:
    """Return a LangSmith-instrumented AsyncOpenAI when tracing env is enabled."""
    if not langsmith_tracing_enabled():
        return client
    try:
        from langsmith.wrappers import wrap_openai
    except ImportError:
        return client
    return wrap_openai(client)
