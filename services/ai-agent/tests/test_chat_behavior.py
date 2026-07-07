"""
FANI chat path — AI behavior tests.

Coverage:
  - Input validation (WardrobeAgent._validate_chat_input)
  - Agent state guards (not-ready errors before any LLM call)
  - History threading (last-10-turns window, role mapping)
  - Wardrobe context injection (route augments message with closet)
  - HTTP chat endpoint: happy path, mode flag, error codes
  - SSE stream endpoint: event sequence, error propagation
  - FANI persona: system prompt identity and tool inventory
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage, HumanMessage

import app.api.v1.agent as agent_routes
from app.agent.wardrobe_agent import WardrobeAgent, _validate_chat_input
from app.agent.prompts import WARDROBE_AGENT_SYSTEM_PROMPT
from app.tools import ALL_TOOLS


# ── helpers ───────────────────────────────────────────────────────────────────

def _turns(n: int) -> list[dict[str, str]]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(n)]


def _closet_items(n: int = 2) -> list[dict[str, Any]]:
    return [
        {"id": f"item-{i}", "name": f"Blue Shirt {i}", "category": "tops",
         "color": "blue", "occasion": ["casual"]}
        for i in range(n)
    ]


# ── 1. Input validation ───────────────────────────────────────────────────────

class TestInputValidation:
    def test_empty_message_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _validate_chat_input("", [])

    def test_whitespace_only_message_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            _validate_chat_input("   \n\t  ", [])

    def test_message_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="4000"):
            _validate_chat_input("x" * 4001, [])

    def test_history_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="50"):
            _validate_chat_input("Hi", _turns(51))

    def test_message_at_max_length_passes(self) -> None:
        _validate_chat_input("x" * 4000, [])  # must not raise

    def test_history_at_max_length_passes(self) -> None:
        _validate_chat_input("Hi", _turns(50))  # must not raise


# ── 2. Agent state guards ─────────────────────────────────────────────────────

class TestAgentStateGuards:
    @pytest.mark.asyncio
    async def test_chat_raises_when_not_started(self) -> None:
        agent = WardrobeAgent()
        with pytest.raises(RuntimeError, match="not started"):
            await agent.chat("Hello")

    @pytest.mark.asyncio
    async def test_stream_raises_when_not_started(self) -> None:
        agent = WardrobeAgent()
        with pytest.raises(RuntimeError, match="not started"):
            # Exhaust the generator to trigger the guard
            async for _ in agent.stream_chat("Hello"):
                pass

    def test_is_ready_false_before_start(self) -> None:
        assert WardrobeAgent().is_ready is False

    def test_is_ready_true_after_mock_start(self, ready_agent: WardrobeAgent) -> None:
        assert ready_agent.is_ready is True


# ── 3. History threading ──────────────────────────────────────────────────────

class TestHistoryThreading:
    @pytest.mark.asyncio
    async def test_only_last_10_turns_sent_to_agent(self, ready_agent: WardrobeAgent) -> None:
        history = _turns(20)  # 20 prior turns — only last 10 should be forwarded
        await ready_agent.chat("New message", history=history)

        call_args = ready_agent._agent.ainvoke.call_args
        messages = call_args[0][0]["messages"]
        # last 10 history turns + 1 new user message = 11 total
        assert len(messages) == 11

    @pytest.mark.asyncio
    async def test_user_turns_become_human_messages(self, ready_agent: WardrobeAgent) -> None:
        history = [{"role": "user", "content": "prior question"}]
        await ready_agent.chat("Follow-up", history=history)

        messages = ready_agent._agent.ainvoke.call_args[0][0]["messages"]
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "prior question"

    @pytest.mark.asyncio
    async def test_assistant_turns_become_ai_messages(self, ready_agent: WardrobeAgent) -> None:
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello! I'm FANI."},
        ]
        await ready_agent.chat("Next", history=history)

        messages = ready_agent._agent.ainvoke.call_args[0][0]["messages"]
        assert isinstance(messages[1], AIMessage)
        assert "FANI" in messages[1].content

    @pytest.mark.asyncio
    async def test_new_message_is_last_in_sequence(self, ready_agent: WardrobeAgent) -> None:
        await ready_agent.chat("The new question", history=_turns(4))

        messages = ready_agent._agent.ainvoke.call_args[0][0]["messages"]
        last = messages[-1]
        assert isinstance(last, HumanMessage)
        assert last.content == "The new question"

    @pytest.mark.asyncio
    async def test_empty_history_sends_single_message(self, ready_agent: WardrobeAgent) -> None:
        await ready_agent.chat("Solo message", history=[])

        messages = ready_agent._agent.ainvoke.call_args[0][0]["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)


# ── 4. Wardrobe context injection ─────────────────────────────────────────────

class TestWardrobeContextInjection:
    def test_format_wardrobe_includes_item_name(self) -> None:
        items = [{"name": "Red Dress", "category": "dresses", "color": "red", "occasion": ["formal"]}]
        result = agent_routes._format_wardrobe(items)
        assert "Red Dress" in result

    def test_format_wardrobe_includes_category_and_color(self) -> None:
        items = [{"name": "Navy Blazer", "category": "outerwear", "color": "navy", "occasion": []}]
        result = agent_routes._format_wardrobe(items)
        assert "outerwear" in result
        assert "navy" in result

    def test_format_wardrobe_handles_list_occasions(self) -> None:
        items = [{"name": "Tee", "category": "tops", "color": "white",
                  "occasion": ["casual", "gym"]}]
        result = agent_routes._format_wardrobe(items)
        assert "casual" in result
        assert "gym" in result

    def test_format_wardrobe_handles_missing_fields(self) -> None:
        items = [{}]  # completely empty item dict
        result = agent_routes._format_wardrobe(items)
        assert "MY WARDROBE" in result  # header still present

    @pytest.mark.asyncio
    async def test_closet_items_appended_to_agent_message(
        self, agent_client: AsyncClient, ready_agent: WardrobeAgent
    ) -> None:
        items = _closet_items(2)
        await agent_client.post(
            "/api/v1/agent/chat",
            json={"message": "What should I wear?", "closet_items": items},
        )
        # The agent's chat() was called with an augmented message
        call_args = ready_agent._agent.ainvoke.call_args
        messages = call_args[0][0]["messages"]
        augmented = messages[-1].content
        assert "Blue Shirt 0" in augmented
        assert "MY WARDROBE" in augmented

    @pytest.mark.asyncio
    async def test_empty_closet_no_wardrobe_block(
        self, agent_client: AsyncClient, ready_agent: WardrobeAgent
    ) -> None:
        await agent_client.post(
            "/api/v1/agent/chat",
            json={"message": "Just a chat message", "closet_items": []},
        )
        messages = ready_agent._agent.ainvoke.call_args[0][0]["messages"]
        augmented = messages[-1].content
        assert "MY WARDROBE" not in augmented

    @pytest.mark.asyncio
    async def test_stylist_instruction_injected_with_closet(
        self, agent_client: AsyncClient
    ) -> None:
        resp = await agent_client.post(
            "/api/v1/agent/chat",
            json={"message": "Suggest an outfit", "closet_items": _closet_items()},
        )
        assert resp.status_code == 200  # sanity: the injection path still succeeds


# ── 5. Chat endpoint HTTP behaviour ──────────────────────────────────────────

class TestChatEndpoint:
    @pytest.mark.asyncio
    async def test_happy_path_returns_200(self, agent_client: AsyncClient) -> None:
        resp = await agent_client.post(
            "/api/v1/agent/chat", json={"message": "What should I wear today?"}
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_response_has_reply_and_mode(self, agent_client: AsyncClient) -> None:
        resp = await agent_client.post(
            "/api/v1/agent/chat", json={"message": "Outfit ideas please"}
        )
        body = resp.json()
        assert "reply" in body
        assert "mode" in body

    @pytest.mark.asyncio
    async def test_mode_is_full_when_tools_present(self, agent_client: AsyncClient) -> None:
        resp = await agent_client.post(
            "/api/v1/agent/chat", json={"message": "Hi FANI"}
        )
        assert resp.json()["mode"] == "full"

    @pytest.mark.asyncio
    async def test_reply_is_string(self, agent_client: AsyncClient) -> None:
        resp = await agent_client.post(
            "/api/v1/agent/chat", json={"message": "Tell me about my wardrobe"}
        )
        assert isinstance(resp.json()["reply"], str)
        assert len(resp.json()["reply"]) > 0

    @pytest.mark.asyncio
    async def test_503_when_agent_not_ready(self, unready_client: AsyncClient) -> None:
        resp = await unready_client.post(
            "/api/v1/agent/chat", json={"message": "Hello"}
        )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_503_when_openai_key_missing(self, no_key_client: AsyncClient) -> None:
        resp = await no_key_client.post(
            "/api/v1/agent/chat", json={"message": "Hello"}
        )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_422_on_empty_message(self, agent_client: AsyncClient) -> None:
        resp = await agent_client.post(
            "/api/v1/agent/chat", json={"message": ""}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_422_on_message_too_long(self, agent_client: AsyncClient) -> None:
        resp = await agent_client.post(
            "/api/v1/agent/chat", json={"message": "x" * 4001}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_500_when_agent_raises(
        self,
        agent_client: AsyncClient,
        ready_agent: WardrobeAgent,
    ) -> None:
        ready_agent._agent.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
        resp = await agent_client.post(
            "/api/v1/agent/chat", json={"message": "Trigger error"}
        )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_history_accepted_in_request(self, agent_client: AsyncClient) -> None:
        history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
        resp = await agent_client.post(
            "/api/v1/agent/chat",
            json={"message": "Follow up", "history": history},
        )
        assert resp.status_code == 200


# ── 6. SSE stream endpoint ────────────────────────────────────────────────────

class TestStreamEndpoint:
    @pytest.mark.asyncio
    async def test_stream_returns_event_stream_content_type(
        self, agent_client: AsyncClient, ready_agent: WardrobeAgent
    ) -> None:
        async def _fake_stream(*_a, **_kw) -> AsyncIterator[str]:
            yield "Hello"

        ready_agent.stream_chat = _fake_stream  # type: ignore[method-assign]

        async with agent_client.stream(
            "POST",
            "/api/v1/agent/chat/stream",
            json={"message": "Stream me"},
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_stream_event_sequence_status_tokens_done(
        self, agent_client: AsyncClient, ready_agent: WardrobeAgent
    ) -> None:
        async def _fake_stream(*_a, **_kw) -> AsyncIterator[str]:
            yield "Hello "
            yield "from FANI."

        ready_agent.stream_chat = _fake_stream  # type: ignore[method-assign]

        events: list[dict] = []
        async with agent_client.stream(
            "POST",
            "/api/v1/agent/chat/stream",
            json={"message": "Tell me something"},
        ) as resp:
            body = await resp.aread()

        for line in body.decode().split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))

        types = [e["type"] for e in events]
        assert types[0] == "status"
        assert "token" in types
        assert types[-1] == "done"

    @pytest.mark.asyncio
    async def test_stream_token_events_carry_content(
        self, agent_client: AsyncClient, ready_agent: WardrobeAgent
    ) -> None:
        async def _fake_stream(*_a, **_kw) -> AsyncIterator[str]:
            yield "Style tip one."

        ready_agent.stream_chat = _fake_stream  # type: ignore[method-assign]

        async with agent_client.stream(
            "POST",
            "/api/v1/agent/chat/stream",
            json={"message": "Quick tip"},
        ) as resp:
            body = await resp.aread()

        tokens = [
            json.loads(line[len("data:"):].strip())
            for line in body.decode().split("\n")
            if line.strip().startswith("data:")
            and json.loads(line[len("data:"):].strip()).get("type") == "token"
        ]
        combined = "".join(t["content"] for t in tokens)
        assert "Style tip one." in combined

    @pytest.mark.asyncio
    async def test_stream_emits_error_event_on_exception(
        self, agent_client: AsyncClient, ready_agent: WardrobeAgent
    ) -> None:
        async def _boom(*_a, **_kw) -> AsyncIterator[str]:
            raise RuntimeError("agent exploded")
            yield  # make it a generator

        ready_agent.stream_chat = _boom  # type: ignore[method-assign]

        async with agent_client.stream(
            "POST",
            "/api/v1/agent/chat/stream",
            json={"message": "Crash please"},
        ) as resp:
            body = await resp.aread()

        events = [
            json.loads(line[len("data:"):].strip())
            for line in body.decode().split("\n")
            if line.strip().startswith("data:")
        ]
        error_events = [e for e in events if e.get("type") == "error"]
        assert error_events, "expected at least one error event"
        # The raw exception text must NOT leak to the client; a generic,
        # user-facing message is returned instead (the real error is logged).
        assert "agent exploded" not in error_events[0]["message"]
        assert error_events[0]["message"] == "Chat failed. Please try again."

    @pytest.mark.asyncio
    async def test_stream_503_when_agent_not_ready(
        self, unready_client: AsyncClient
    ) -> None:
        async with unready_client.stream(
            "POST",
            "/api/v1/agent/chat/stream",
            json={"message": "Hello"},
        ) as resp:
            assert resp.status_code == 503


# ── 7. FANI persona and tool inventory ───────────────────────────────────────

class TestSystemPromptPersona:
    def test_fani_identity_present_in_system_prompt(self) -> None:
        assert "CLOZEHIVE AI" in WARDROBE_AGENT_SYSTEM_PROMPT

    def test_system_prompt_describes_wardrobe_behaviour(self) -> None:
        assert "wardrobe" in WARDROBE_AGENT_SYSTEM_PROMPT.lower()

    def test_system_prompt_covers_packing_two_step(self) -> None:
        # Decision rule 1 requires get_weather_summary before the packing checklist
        assert "get_weather_summary" in WARDROBE_AGENT_SYSTEM_PROMPT
        assert "get_packing_checklist" in WARDROBE_AGENT_SYSTEM_PROMPT

    def test_system_prompt_instructs_only_use_wardrobe_items(self) -> None:
        # "Flag missing wardrobe items clearly" tells the agent to surface gaps
        # rather than invent items not in the user's closet.
        assert "Flag missing wardrobe items" in WARDROBE_AGENT_SYSTEM_PROMPT

    def test_all_tool_names_listed_in_system_prompt(self) -> None:
        missing = [t.name for t in ALL_TOOLS if t.name not in WARDROBE_AGENT_SYSTEM_PROMPT]
        assert missing == [], f"Tool(s) not mentioned in system prompt: {missing}"


class TestToolInventory:
    def test_five_tools_registered(self) -> None:
        assert len(ALL_TOOLS) == 5

    def test_tool_names_are_unique(self) -> None:
        names = [t.name for t in ALL_TOOLS]
        assert len(names) == len(set(names))

    def test_weather_tools_present(self) -> None:
        names = {t.name for t in ALL_TOOLS}
        assert "get_weather_forecast" in names
        assert "get_weather_summary" in names

    def test_outfit_tools_present(self) -> None:
        names = {t.name for t in ALL_TOOLS}
        assert "generate_outfit_suggestions" in names
        assert "get_outfit_style_tips" in names

    def test_packing_tools_present(self) -> None:
        names = {t.name for t in ALL_TOOLS}
        assert "get_packing_checklist" in names
        # Wardrobe-matched packing now lives solely in the api-gateway
        # packing_service — the agent no longer carries a duplicate.
        assert "generate_trip_packing_list" not in names

    def test_all_tools_are_callable(self) -> None:
        # LangChain @tool objects expose __call__; async tools store the
        # coroutine in .coroutine rather than .func.
        for tool in ALL_TOOLS:
            has_func = getattr(tool, "func", None) is not None
            has_coro = getattr(tool, "coroutine", None) is not None
            assert has_func or has_coro, f"{tool.name} has neither .func nor .coroutine"
