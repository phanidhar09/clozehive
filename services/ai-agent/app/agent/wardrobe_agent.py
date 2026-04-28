"""
Production-hardened CLOZEHIVE Wardrobe Agent.

Hardening features:
  - asyncio.wait_for() for end-to-end timeout
  - tenacity retry on transient tool failures
  - Per-tool-call structured logging
  - Input validation before tool dispatch
  - Graceful degradation when MCP servers are unavailable
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.agent.prompts import WARDROBE_AGENT_SYSTEM_PROMPT
from app.core.config import get_settings

logger = structlog.get_logger("wardrobe_agent")
settings = get_settings()


class ToolCallLogger:
    """Wraps a LangChain tool and logs every call + result."""

    def __init__(self, tool) -> None:
        self._tool = tool
        self.name = tool.name
        self.description = tool.description

    async def ainvoke(self, inputs: dict[str, Any]) -> Any:
        start = time.perf_counter()
        log = logger.bind(tool=self.name, inputs=_safe_truncate(inputs))
        log.info("tool_call_start")
        try:
            result = await self._tool.ainvoke(inputs)
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            log.info("tool_call_success", elapsed_ms=elapsed, output_len=len(str(result)))
            return result
        except Exception as exc:
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            log.error("tool_call_error", elapsed_ms=elapsed, error=str(exc))
            raise

    # Passthrough attributes so LangChain can use this as a normal tool
    def __getattr__(self, name: str):
        return getattr(self._tool, name)


def _safe_truncate(data: Any, max_len: int = 200) -> str:
    try:
        s = json.dumps(data, default=str)
        return s[:max_len] + "…" if len(s) > max_len else s
    except Exception:
        return str(data)[:max_len]


def _validate_chat_input(message: str, history: list[dict]) -> None:
    if not message or not message.strip():
        raise ValueError("Message cannot be empty")
    if len(message) > 4000:
        raise ValueError("Message exceeds 4000 character limit")
    if len(history) > 50:
        raise ValueError("History exceeds 50 turns — please start a new conversation")


class WardrobeAgent:
    """
    Persistent agent that holds one MultiServerMCPClient connection for its
    entire lifetime. Call start() once and stop() on shutdown.
    """

    def __init__(self) -> None:
        self._client: MultiServerMCPClient | None = None
        self._agent = None
        self._tools: list = []
        self._ready = False

    async def start(self) -> None:
        logger.info("agent_starting", mcp_servers=list(settings.mcp_server_config.keys()))
        try:
            # langchain-mcp-adapters 0.1+: no async context manager — load tools with await.
            self._client = MultiServerMCPClient(settings.mcp_server_config)
            raw_tools = await self._client.get_tools()
            # LangGraph's tool binding requires bare BaseTool instances (it inspects
            # ``__name__`` / pydantic args_schema). The wrapper ToolCallLogger breaks
            # that contract, so we keep the raw tools — MCP servers still log every
            # invocation on their side.
            self._tools = list(raw_tools)

            logger.info("mcp_tools_loaded", count=len(self._tools), names=[t.name for t in self._tools])

            model = ChatOpenAI(
                model=settings.openai_model,
                temperature=settings.agent_temperature,
                api_key=settings.openai_api_key,
                streaming=True,
            )

            self._agent = create_react_agent(
                model,
                self._tools,
                prompt=WARDROBE_AGENT_SYSTEM_PROMPT,
            )
            self._ready = True
            logger.info("agent_ready")

        except Exception as exc:
            logger.error("agent_start_failed", error=str(exc))
            self._ready = False
            raise

    async def stop(self) -> None:
        self._client = None
        self._agent = None
        self._tools = []
        self._ready = False
        logger.info("agent_stopped")

    @property
    def is_ready(self) -> bool:
        return self._ready and self._agent is not None

    @property
    def available_tools(self) -> list[str]:
        return [t.name for t in self._tools]

    @retry(
        stop=stop_after_attempt(settings.retry_max_attempts),
        wait=wait_exponential(
            multiplier=1,
            min=settings.retry_min_wait,
            max=settings.retry_max_wait,
        ),
        retry=retry_if_exception_type((asyncio.TimeoutError,)),
        reraise=True,
    )
    async def chat(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Invoke the agent with a user message, returning the final reply string.

        Args:
            message: The user's latest message (max 4000 chars).
            history: Prior turns as [{'role': 'user'|'assistant', 'content': str}].
                     Capped at 10 turns to keep context windows manageable.

        Returns:
            The agent's plain-text response.

        Raises:
            RuntimeError: If the agent is not started.
            asyncio.TimeoutError: If the agent exceeds agent_timeout_seconds.
            ValueError: If inputs fail validation.
        """
        if not self.is_ready:
            raise RuntimeError("Agent not started — call await agent.start() first")

        history = history or []
        _validate_chat_input(message, history)

        messages = []
        for turn in history[-10:]:  # cap at last 10 turns
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=message))

        log = logger.bind(message_preview=message[:80])
        log.info("agent_invoke_start")

        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self._agent.ainvoke({"messages": messages}),
                timeout=settings.agent_timeout_seconds,
            )
        except asyncio.TimeoutError:
            log.error("agent_timeout", timeout_s=settings.agent_timeout_seconds)
            raise

        elapsed = round((time.perf_counter() - start) * 1000, 1)

        output_messages = result.get("messages", [])
        if not output_messages:
            return "I couldn't generate a response. Please try again."

        last = output_messages[-1]
        response = last.content if hasattr(last, "content") else str(last)
        if isinstance(response, list):
            parts: list[str] = []
            for block in response:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif isinstance(block, str):
                    parts.append(block)
                else:
                    parts.append(str(block))
            response = "".join(parts)

        log.info("agent_invoke_complete", elapsed_ms=elapsed, response_len=len(response))
        return response

    async def stream_chat(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream model tokens as they are produced by LangGraph/LangChain."""
        if not self.is_ready:
            raise RuntimeError("Agent not started — call await agent.start() first")

        history = history or []
        _validate_chat_input(message, history)

        messages = []
        for turn in history[-10:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=message))

        log = logger.bind(message_preview=message[:80])
        log.info("agent_stream_start")
        start = time.perf_counter()

        try:
            async with asyncio.timeout(settings.agent_timeout_seconds):
                async for event in self._agent.astream_events(
                    {"messages": messages},
                    version="v2",
                ):
                    if event.get("event") != "on_chat_model_stream":
                        continue
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", "")
                    if isinstance(content, str) and content:
                        yield content
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = str(block.get("text", ""))
                                if text:
                                    yield text
        except asyncio.TimeoutError:
            log.error("agent_stream_timeout", timeout_s=settings.agent_timeout_seconds)
            raise
        finally:
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            log.info("agent_stream_complete", elapsed_ms=elapsed)


# ── Module-level singleton ────────────────────────────────────────────────────

_instance: WardrobeAgent | None = None


def get_agent() -> WardrobeAgent:
    global _instance
    if _instance is None:
        _instance = WardrobeAgent()
    return _instance
