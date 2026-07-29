"""Bounded tool-calling agent loop.

The rest of the AI stack is fixed pipelines: the code decides what to fetch, in
what order, before the model sees anything. This module is the exception — the
model chooses which tools to call and when, which is worth it only where the
*second* question genuinely depends on the first answer.

Everything here is deliberately constrained, because an unbounded loop over a
user's wardrobe is a cost and safety problem:

* **Bounded** — hard iteration cap; on reaching it the loop makes one final
  no-tools call so the user still gets an answer instead of nothing.
* **Allowlisted** — the model can only invoke tools present in the registry it
  was handed. An unknown name comes back as a tool *result* describing the
  error, so the model can recover instead of the request failing.
* **Sequential** — tool handlers run one at a time, never ``asyncio.gather``.
  Handlers share the request's ``AsyncSession``, and fanning concurrent queries
  over one session is what caused the chat "I'm having a moment" failures.
* **Timeboxed** — every handler runs under ``asyncio.wait_for`` so one hung
  dependency can't wedge the run.
* **Untrusted output** — tool results re-enter the prompt as ``tool`` messages,
  which look authoritative to the model. Results are truncated and wrapped with
  :func:`app.core.llm_safety.wrap_untrusted`, the same treatment web-intel text
  gets, so injected text arriving via a tool is fenced as data.

The returned :class:`AgentRun` carries the full step transcript. Callers need it
for more than debugging: on a fixed pipeline the caller knows what context was
fetched, but here that is only knowable after the fact — grounding checks derive
their provenance flags from ``tools_used``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.api.v1.intelligence.services import ai_service
from app.core.analytics import LLMTelemetry
from app.core.llm_safety import wrap_untrusted
from app.core.logging import get_logger

logger = get_logger("agent_loop")

__all__ = ["AgentRun", "AgentStep", "AgentTool", "run_agent_loop"]

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class AgentTool:
    """One callable the model may invoke.

    ``parameters`` is a JSON Schema object. Keep it narrow — every optional field
    is another chance for the model to pass something the handler must defend
    against.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    # Label used when fencing this tool's output as untrusted data in the prompt.
    result_label: str = "Tool result"

    def to_schema(self) -> dict[str, Any]:
        """OpenAI tool schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentStep:
    """One executed tool call — the audit trail for a run."""

    iteration: int
    tool: str
    arguments: dict[str, Any]
    ok: bool
    duration_ms: int
    error: str | None = None


@dataclass
class AgentRun:
    """Outcome of a loop.

    ``stop_reason`` is one of:
      ``answered``        — the model returned prose with no further tool calls
      ``max_iterations``  — hit the cap; ``text`` is from the forced final call
      ``llm_error``       — provider failure; ``text`` is the user-safe message
    """

    text: str
    steps: list[AgentStep] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str = "answered"
    is_error: bool = False

    @property
    def tools_used(self) -> list[str]:
        """Distinct tools that returned successfully, in first-call order."""
        seen: list[str] = []
        for step in self.steps:
            if step.ok and step.tool not in seen:
                seen.append(step.tool)
        return seen


def _serialise_result(value: Any, *, max_chars: int) -> str:
    """JSON-encode a handler's return value, truncated to a char budget.

    Truncation is a cost guard: a 200-item closet dump would blow the context
    window and the token bill. Handlers should pre-summarise; this is the backstop.
    """
    try:
        text = json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > max_chars:
        text = text[:max_chars] + f"… [truncated at {max_chars} chars]"
    return text


async def _run_tool(
    tool: AgentTool,
    arguments: dict[str, Any],
    *,
    timeout_seconds: float,
) -> tuple[bool, Any]:
    """Execute one handler under a timeout. Returns ``(ok, result_or_error)``.

    Never raises — a failing tool is data the model can react to ("that lookup
    failed, answer from what you have"), not a failed request.
    """
    try:
        result = await asyncio.wait_for(tool.handler(arguments), timeout=timeout_seconds)
        return True, result
    except TimeoutError:
        logger.warning("agent_tool_timeout", tool=tool.name, timeout=timeout_seconds)
        return False, f"Tool '{tool.name}' timed out after {timeout_seconds:g}s."
    except Exception as exc:  # noqa: BLE001 — a broken tool must not kill the run
        logger.warning("agent_tool_failed", tool=tool.name, error=str(exc))
        return False, f"Tool '{tool.name}' failed: {type(exc).__name__}."


async def run_agent_loop(
    *,
    system_prompt: str,
    user_message: str,
    tools: list[AgentTool],
    model: str,
    max_iterations: int,
    tool_timeout_seconds: float,
    tool_result_max_chars: int = 4000,
    max_tokens: int | None = None,
    temperature: float = 0.3,
    telemetry: LLMTelemetry | None = None,
) -> AgentRun:
    """Drive a tool-calling model until it answers or hits the iteration cap.

    ``user_message`` must already be sanitised by the caller (it is user-controlled
    text). Tool *output* is fenced here.
    """
    registry = {tool.name: tool for tool in tools}
    schemas = [tool.to_schema() for tool in tools]
    transcript: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    steps: list[AgentStep] = []

    for iteration in range(1, max_iterations + 1):
        turn = await ai_service.chat_with_tools(
            transcript,
            system_prompt,
            tools=schemas,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            telemetry=telemetry,
        )
        if turn.is_error:
            return AgentRun(
                text=turn.content or "",
                steps=steps,
                iterations=iteration,
                stop_reason="llm_error",
                is_error=True,
            )

        # No tool calls — the model is answering.
        if not turn.tool_calls:
            logger.info(
                "agent_run_complete",
                iterations=iteration,
                tools_used=[s.tool for s in steps if s.ok],
                stop_reason="answered",
            )
            return AgentRun(
                text=turn.content or "",
                steps=steps,
                iterations=iteration,
                stop_reason="answered",
            )

        transcript.append(turn.assistant_message)

        # Sequential by design — see the module docstring on shared sessions.
        for call in turn.tool_calls:
            started = time.perf_counter()
            try:
                arguments = json.loads(call.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                arguments = {}
                ok, payload = False, f"Could not parse arguments for '{call.name}': {exc}."
                tool = None
            else:
                tool = registry.get(call.name)
                if tool is None:
                    # Hallucinated tool name. Tell the model what it may call
                    # rather than failing the request.
                    ok, payload = (
                        False,
                        (f"Unknown tool '{call.name}'. Available tools: {', '.join(sorted(registry))}."),
                    )
                    logger.warning("agent_unknown_tool", tool=call.name)
                else:
                    ok, payload = await _run_tool(tool, arguments, timeout_seconds=tool_timeout_seconds)

            duration_ms = int((time.perf_counter() - started) * 1000)
            steps.append(
                AgentStep(
                    iteration=iteration,
                    tool=call.name,
                    arguments=arguments,
                    ok=ok,
                    duration_ms=duration_ms,
                    error=None if ok else str(payload),
                )
            )

            if ok:
                label = tool.result_label if tool else call.name
                content = wrap_untrusted(label, _serialise_result(payload, max_chars=tool_result_max_chars))
            else:
                # Errors are our own text, not user data — no fencing needed.
                content = str(payload)

            transcript.append({"role": "tool", "tool_call_id": call.id, "content": content})

    # Cap reached with the model still asking for tools. One final no-tools call
    # so the user gets the best answer available from what was already gathered.
    logger.info("agent_max_iterations", max_iterations=max_iterations, tools_used=[s.tool for s in steps if s.ok])
    transcript.append(
        {
            "role": "user",
            "content": (
                "You have reached the research limit for this question. "
                "Answer now using only what you have already gathered, and say plainly "
                "if something could not be checked."
            ),
        }
    )
    final = await ai_service.chat_with_tools(
        transcript,
        system_prompt,
        tools=None,  # forbids further tool calls — guarantees prose back
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        telemetry=telemetry,
    )
    return AgentRun(
        text=final.content or "",
        steps=steps,
        iterations=max_iterations,
        stop_reason="max_iterations",
        is_error=final.is_error,
    )
