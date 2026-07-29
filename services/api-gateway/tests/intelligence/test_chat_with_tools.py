"""``ai_service.chat_with_tools`` — response parsing at the OpenAI SDK boundary.

The loop tests stub ``chat_with_tools`` wholesale, so these cover what that stub
hides: turning a real completion object into a :class:`ToolTurn`, and echoing the
assistant turn back in the shape the API requires on the follow-up request.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.api.v1.intelligence.services import ai_service
from app.api.v1.intelligence.services.agents.loop import AgentTool, run_agent_loop

AI_MODULE = "app.api.v1.intelligence.services.ai_service"


def _completion(
    *,
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str = "stop",
) -> SimpleNamespace:
    """A stand-in for an OpenAI ChatCompletion object."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
    )


def _sdk_tool_call(call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def _fake_client(monkeypatch, responses: list[Any]) -> list[dict[str, Any]]:
    """Install a scripted OpenAI client; return the list of request payloads."""
    requests: list[dict[str, Any]] = []
    queue = list(responses)

    async def create(**kwargs):
        requests.append(kwargs)
        return queue.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(f"{AI_MODULE}._get_client", lambda: client)
    monkeypatch.setattr(f"{AI_MODULE}.settings.openai_api_key", "test-key", raising=False)
    return requests


@pytest.mark.asyncio
async def test_parses_a_text_answer(monkeypatch):
    _fake_client(monkeypatch, [_completion(content="You own 12 items.")])

    turn = await ai_service.chat_with_tools([{"role": "user", "content": "hi"}], "system")

    assert turn.content == "You own 12 items."
    assert turn.tool_calls == []
    assert turn.is_error is False
    assert turn.assistant_message == {"role": "assistant", "content": "You own 12 items."}


@pytest.mark.asyncio
async def test_parses_tool_calls(monkeypatch):
    """A tool call must survive as id + name + raw argument JSON."""
    requests = _fake_client(
        monkeypatch,
        [
            _completion(
                tool_calls=[_sdk_tool_call("call_abc", "get_wardrobe_stats", '{"limit": 5}')],
                finish_reason="tool_calls",
            )
        ],
    )

    tools = [{"type": "function", "function": {"name": "get_wardrobe_stats", "parameters": {}}}]
    turn = await ai_service.chat_with_tools([{"role": "user", "content": "hi"}], "system", tools=tools)

    assert len(turn.tool_calls) == 1
    call = turn.tool_calls[0]
    assert (call.id, call.name, call.arguments) == ("call_abc", "get_wardrobe_stats", '{"limit": 5}')
    assert turn.finish_reason == "tool_calls"
    # The assistant turn must echo the call id — the API rejects tool results
    # that don't match an assistant tool_call.
    assert turn.assistant_message["tool_calls"][0]["id"] == "call_abc"
    assert turn.assistant_message["tool_calls"][0]["function"]["name"] == "get_wardrobe_stats"
    assert requests[0]["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_omits_tools_when_none_given(monkeypatch):
    """No tools means no ``tools`` key — how the loop forces a final answer."""
    requests = _fake_client(monkeypatch, [_completion(content="done")])

    await ai_service.chat_with_tools([{"role": "user", "content": "hi"}], "system", tools=None)

    assert "tools" not in requests[0]
    assert "tool_choice" not in requests[0]


@pytest.mark.asyncio
async def test_tool_role_messages_survive_normalisation(monkeypatch):
    """``tool`` and tool-carrying ``assistant`` messages must reach the API.

    The plain-chat normaliser drops every role except user/assistant; if the tool
    path reused it, the follow-up request would 400.
    """
    requests = _fake_client(monkeypatch, [_completion(content="ok")])

    transcript = [
        {"role": "user", "content": "what should I buy?"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "[USER DATA: stats]\n{}\n[END USER DATA]"},
    ]
    await ai_service.chat_with_tools(transcript, "system")

    roles = [m["role"] for m in requests[0]["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]


@pytest.mark.asyncio
async def test_malformed_tool_call_is_skipped(monkeypatch):
    """A tool call with no function name is unusable — drop it, don't crash."""
    _fake_client(
        monkeypatch,
        [
            _completion(
                tool_calls=[
                    SimpleNamespace(id="c1", function=SimpleNamespace(name=None, arguments="{}")),
                    _sdk_tool_call("c2", "search_closet", "{}"),
                ],
                finish_reason="tool_calls",
            )
        ],
    )

    turn = await ai_service.chat_with_tools([{"role": "user", "content": "hi"}], "system")

    assert [c.name for c in turn.tool_calls] == ["search_closet"]


@pytest.mark.asyncio
async def test_missing_api_key_returns_an_error_turn(monkeypatch):
    monkeypatch.setattr(f"{AI_MODULE}.settings.openai_api_key", "", raising=False)

    turn = await ai_service.chat_with_tools([{"role": "user", "content": "hi"}], "system")

    assert turn.is_error is True
    assert turn.tool_calls == []


@pytest.mark.asyncio
async def test_provider_error_returns_a_safe_turn(monkeypatch):
    """A non-retryable API error becomes an error turn, never an exception."""
    from openai import APIError

    async def create(**kwargs):
        raise APIError("boom", request=None, body=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(f"{AI_MODULE}._get_client", lambda: client)
    monkeypatch.setattr(f"{AI_MODULE}.settings.openai_api_key", "test-key", raising=False)

    turn = await ai_service.chat_with_tools([{"role": "user", "content": "hi"}], "system")

    assert turn.is_error is True
    assert "temporarily unavailable" in (turn.content or "")


@pytest.mark.asyncio
async def test_end_to_end_loop_against_a_fake_sdk(monkeypatch):
    """Full path: loop → chat_with_tools → SDK parsing → tool → final answer."""
    requests = _fake_client(
        monkeypatch,
        [
            _completion(
                tool_calls=[_sdk_tool_call("c1", "get_stats", '{"detail": "full"}')],
                finish_reason="tool_calls",
            ),
            _completion(content="You own 12 items; 3 are unworn."),
        ],
    )

    received: list[dict[str, Any]] = []

    async def handler(args: dict[str, Any]) -> Any:
        received.append(args)
        return {"total_items": 12, "unworn": 3}

    tool = AgentTool(
        name="get_stats",
        description="wardrobe stats",
        parameters={"type": "object", "properties": {}},
        handler=handler,
        result_label="Wardrobe statistics",
    )

    run = await run_agent_loop(
        system_prompt="You are FANI.",
        user_message="what am I not wearing?",
        tools=[tool],
        model="gpt-4o",
        max_iterations=5,
        tool_timeout_seconds=5.0,
    )

    assert run.text == "You own 12 items; 3 are unworn."
    assert run.stop_reason == "answered"
    assert run.tools_used == ["get_stats"]
    # Arguments the model sent reached the handler intact.
    assert received == [{"detail": "full"}]
    # The second request carries the fenced tool result keyed to the call id.
    follow_up = requests[1]["messages"]
    tool_msg = next(m for m in follow_up if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "c1"
    assert "[USER DATA: Wardrobe statistics]" in tool_msg["content"]
    assert '"total_items": 12' in tool_msg["content"]
