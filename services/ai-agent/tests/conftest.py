"""Shared fixtures for ai-agent tests — no network, no OpenAI, no Postgres."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

import app.api.v1.agent as agent_routes
from app.agent.wardrobe_agent import WardrobeAgent
from app.api.v1.agent import router as agent_router
from app.core.config import Settings

# A key that passes Settings.has_valid_openai_key (starts with "sk-", not in blacklist)
_VALID_KEY = "sk-alive-and-well-for-tests"


def _lg_result(reply: str = "FANI reply.") -> dict[str, Any]:
    """Build a LangGraph-shaped output dict with a single AIMessage."""
    return {"messages": [AIMessage(content=reply)]}


# ── Agent fixtures ────────────────────────────────────────────────────────────

@pytest.fixture()
def ready_agent() -> WardrobeAgent:
    """WardrobeAgent whose internal LangGraph mock returns a canned reply."""
    agent = WardrobeAgent()
    mock_lg = MagicMock()
    mock_lg.ainvoke = AsyncMock(return_value=_lg_result("FANI reply."))
    agent._agent = mock_lg
    agent._ready = True
    return agent


@pytest.fixture()
def unready_agent() -> WardrobeAgent:
    """WardrobeAgent that has never been started."""
    return WardrobeAgent()


# ── Settings fixture ──────────────────────────────────────────────────────────

@pytest.fixture()
def fake_settings() -> Settings:
    return Settings(openai_api_key=_VALID_KEY)


# ── HTTP client fixtures ──────────────────────────────────────────────────────

def _build_test_app() -> FastAPI:
    """Minimal FastAPI app with only the agent router — no lifespan."""
    app = FastAPI()
    app.include_router(agent_router, prefix="/api/v1")
    return app


@pytest_asyncio.fixture()
async def agent_client(
    ready_agent: WardrobeAgent,
    fake_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """HTTPX test client wired to a ready agent and a valid OpenAI key."""
    monkeypatch.setattr(agent_routes, "get_agent", lambda: ready_agent)
    monkeypatch.setattr(agent_routes, "settings", fake_settings)
    # Stub out vector store so tests that set user_id don't hit Postgres.
    monkeypatch.setattr(
        agent_routes, "search_closet_context", AsyncMock(return_value=[])
    )
    app = _build_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture()
async def unready_client(
    unready_agent: WardrobeAgent,
    fake_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """HTTPX test client whose agent has not been started."""
    monkeypatch.setattr(agent_routes, "get_agent", lambda: unready_agent)
    monkeypatch.setattr(agent_routes, "settings", fake_settings)
    app = _build_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture()
async def no_key_client(
    ready_agent: WardrobeAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    """HTTPX test client with an unconfigured OpenAI key."""
    monkeypatch.setattr(agent_routes, "get_agent", lambda: ready_agent)
    monkeypatch.setattr(agent_routes, "settings", Settings(openai_api_key=""))
    app = _build_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
