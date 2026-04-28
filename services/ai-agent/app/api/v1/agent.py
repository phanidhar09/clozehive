"""AI Agent routes — /api/v1/agent/*"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.wardrobe_agent import get_agent
from app.services.vector_store import search_closet_context

router = APIRouter(prefix="/agent", tags=["Agent"])


def _mcp_output_to_str(raw: Any) -> str:
    """MCP tools may return a plain string or LangChain-style content blocks."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(raw)


def _parse_json_mcp(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    text = _mcp_output_to_str(raw).strip()
    if not text:
        raise ValueError("empty MCP tool output")
    return json.loads(text)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)
    closet_items: list[dict[str, Any]] = Field(default_factory=list)
    user_id: str | None = None


class ChatResponse(BaseModel):
    reply: str


class OutfitRequest(BaseModel):
    closet_items: list[dict[str, Any]]
    occasion: str = "casual"
    weather: str = "mild"
    temperature: float = 20.0


class PackingRequest(BaseModel):
    destination: str
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    purpose: str = "general"
    closet_items: list[dict[str, Any]] = Field(default_factory=list)


class VisionRequest(BaseModel):
    image_base64: str
    media_type: str = "image/jpeg"


def _require_agent():
    agent = get_agent()
    if not agent.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI agent not ready — MCP servers may be starting up",
        )
    return agent


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    """Full agent-orchestrated wardrobe chat."""
    agent = _require_agent()

    # Enrich message with closet context
    message = body.message
    if body.closet_items:
        message += f"\n\n[User's closet ({len(body.closet_items)} items)]:\n{json.dumps(body.closet_items)}"
    if body.user_id:
        vector_matches = await search_closet_context(body.user_id, body.message)
        if vector_matches:
            message += f"\n\n[Relevant wardrobe memory]:\n{json.dumps(vector_matches, default=str)}"

    try:
        reply = await agent.chat(message, history=body.history)
        return ChatResponse(reply=reply)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest):
    """True token stream from LangGraph/LangChain to the API gateway."""
    agent = _require_agent()

    message = body.message
    if body.closet_items:
        message += f"\n\n[User's closet ({len(body.closet_items)} items)]:\n{json.dumps(body.closet_items)}"
    if body.user_id:
        vector_matches = await search_closet_context(body.user_id, body.message)
        if vector_matches:
            message += f"\n\n[Relevant wardrobe memory]:\n{json.dumps(vector_matches, default=str)}"

    async def events():
        try:
            yield _sse({"type": "status", "message": "Thinking..."})
            async for token in agent.stream_chat(message, history=body.history):
                yield _sse({"type": "token", "content": token})
            yield _sse({"type": "done"})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/outfit")
async def outfit(body: OutfitRequest):
    """Generate outfit suggestions via the outfit MCP tool."""
    agent = _require_agent()
    outfit_tool = next((t for t in agent._tools if "generate_outfit" in t.name), None)
    if not outfit_tool:
        raise HTTPException(status_code=503, detail="Outfit tool unavailable")

    try:
        raw = await outfit_tool.ainvoke({
            "closet_items_json": json.dumps(body.closet_items),
            "occasion": body.occasion,
            "weather": body.weather,
            "temperature": body.temperature,
        })
        return _parse_json_mcp(raw)
    except HTTPException:
        raise
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid outfit JSON from MCP: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/packing")
async def packing(body: PackingRequest):
    """Call weather MCP then packing MCP for a structured PackingResult JSON."""
    agent = _require_agent()
    weather_tool = next((t for t in agent._tools if "get_weather_summary" in t.name), None)
    packing_tool = next((t for t in agent._tools if "generate_trip_packing_list" in t.name), None)
    if not weather_tool or not packing_tool:
        raise HTTPException(
            status_code=503,
            detail="Weather or packing MCP tool unavailable",
        )

    try:
        wraw = await weather_tool.ainvoke({
            "destination": body.destination,
            "start_date": body.start_date,
            "end_date": body.end_date,
        })
        weather_data = _parse_json_mcp(wraw)
        if isinstance(weather_data, dict) and weather_data.get("error"):
            raise HTTPException(status_code=502, detail=str(weather_data["error"]))

        weather_json = json.dumps(weather_data)
        praw = await packing_tool.ainvoke({
            "destination": body.destination,
            "start_date": body.start_date,
            "end_date": body.end_date,
            "purpose": body.purpose,
            "closet_items_json": json.dumps(body.closet_items),
            "weather_summary_json": weather_json,
        })
        result = _parse_json_mcp(praw)
        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(status_code=502, detail=str(result["error"]))
        return result
    except HTTPException:
        raise
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid packing JSON from MCP: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/vision/analyze")
async def vision_analyze(body: VisionRequest):
    """Analyze garment image via the vision MCP tool."""
    agent = _require_agent()
    vision_tool = next(
        (t for t in agent._tools if "analyze_clothing" in t.name and "from_bytes" not in t.name),
        None,
    )
    if not vision_tool:
        raise HTTPException(status_code=503, detail="Vision tool unavailable")

    try:
        raw = await vision_tool.ainvoke({
            "image_base64": body.image_base64,
            "media_type": body.media_type,
        })
        return _parse_json_mcp(raw)
    except HTTPException:
        raise
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid vision JSON from MCP: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
