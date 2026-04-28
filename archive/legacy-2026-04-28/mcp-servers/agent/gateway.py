"""
CLOZEHIVE AI Gateway — FastAPI server — port 8005
==================================================
HTTP entry-point that bridges the Node.js backend (and frontend) to the
LangChain + MCP wardrobe agent.

Routes
------
POST  /chat              — wardrobe chat (agent-orchestrated)
POST  /outfit            — outfit suggestions (direct outfit tool)
POST  /packing           — travel packing list (agent-orchestrated)
POST  /vision/analyze    — garment image analysis (direct vision tool)
GET   /tools             — list all available MCP tools
GET   /health            — service health + tool count

Run:
    python gateway.py
    # or
    uvicorn gateway:app --host 0.0.0.0 --port 8005 --reload
"""

from __future__ import annotations

import base64
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.logger import get_logger
from agent import WardrobeAgent

logger = get_logger("gateway")
settings = get_settings()

# ── Pydantic request / response schemas ───────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)
    closet_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional — automatically appended to the message as context.",
    )

class ChatResponse(BaseModel):
    reply: str
    tool_calls_made: int = 0


class OutfitRequest(BaseModel):
    closet_items: list[dict[str, Any]] = Field(..., min_length=1)
    occasion: str = "casual"
    weather: str = "mild"
    temperature: float = 20.0

class OutfitResponse(BaseModel):
    outfits: list[dict[str, Any]]
    occasion: str
    weather: str
    temperature: float


class PackingRequest(BaseModel):
    destination: str
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str   = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    purpose: str    = "general"
    closet_items: list[dict[str, Any]] = Field(default_factory=list)


class ToolInfo(BaseModel):
    name: str
    description: str


# ── App lifespan (agent lifecycle) ────────────────────────────────────────────

_agent: WardrobeAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent

    logger.info("Gateway starting — connecting to MCP servers …")
    _agent = WardrobeAgent()

    try:
        await _agent.start()
        logger.info("Gateway ready — %d tools available", len(_agent.available_tools))
    except Exception as exc:
        logger.error("Failed to connect to MCP servers: %s", exc, exc_info=True)
        logger.warning("Gateway will start in degraded mode — agent unavailable")

    yield  # ── server is running ──

    if _agent:
        await _agent.stop()
    logger.info("Gateway shutdown complete")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="CLOZEHIVE AI Gateway",
    description=(
        "FastAPI gateway that connects the wardrobe application to the "
        "LangChain + MCP AI layer. Handles chat, outfit generation, "
        "travel packing, and garment vision analysis."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Dependency helper ─────────────────────────────────────────────────────────

def _require_agent() -> WardrobeAgent:
    if _agent is None or _agent._agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI agent is not available — ensure all MCP servers are running.",
        )
    return _agent


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Meta"])
async def health() -> dict[str, Any]:
    """Service health check."""
    agent_ok = _agent is not None and _agent._agent is not None
    return {
        "status": "ok" if agent_ok else "degraded",
        "service": "clozehive-ai-gateway",
        "version": "1.0.0",
        "agent_ready": agent_ok,
        "tools_available": len(_agent.available_tools) if agent_ok else 0,
        "mcp_servers": {
            "weather": settings.weather_sse_url,
            "outfit":  settings.outfit_sse_url,
            "packing": settings.packing_sse_url,
            "vision":  settings.vision_sse_url,
        },
    }


@app.get("/tools", response_model=list[ToolInfo], tags=["Meta"])
async def list_tools() -> list[ToolInfo]:
    """List all tools available from connected MCP servers."""
    agent = _require_agent()
    return [
        ToolInfo(
            name=t.name,
            description=(t.description or "")[:200],
        )
        for t in agent._tools
    ]


@app.post("/chat", response_model=ChatResponse, tags=["AI"])
async def chat(req: ChatRequest) -> ChatResponse:
    """
    Send a message to the wardrobe AI agent.
    The agent will autonomously decide which MCP tools to call
    (weather, outfit, packing, vision) to answer the question.

    Include closet_items to give the agent wardrobe context.
    """
    agent = _require_agent()

    # Enrich message with closet context if provided
    message = req.message
    if req.closet_items:
        closet_json = json.dumps(req.closet_items, indent=2)
        message = (
            f"{req.message}\n\n"
            f"[User's closet ({len(req.closet_items)} items)]:\n{closet_json}"
        )

    try:
        reply = await agent.chat(message, history=req.history)
        return ChatResponse(reply=reply)
    except Exception as exc:
        logger.error("Chat error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")


@app.post("/outfit", response_model=OutfitResponse, tags=["AI"])
async def outfit(req: OutfitRequest) -> OutfitResponse:
    """
    Generate 3 outfit suggestions from the user's closet.
    Calls the outfit MCP server directly (no full agent reasoning needed).
    """
    agent = _require_agent()

    # Find the outfit generation tool directly
    outfit_tool = next(
        (t for t in agent._tools if "generate_outfit" in t.name),
        None,
    )
    if not outfit_tool:
        raise HTTPException(status_code=503, detail="Outfit tool not available")

    try:
        raw = await outfit_tool.ainvoke({
            "closet_items_json": json.dumps(req.closet_items),
            "occasion": req.occasion,
            "weather": req.weather,
            "temperature": req.temperature,
        })
        data = json.loads(raw) if isinstance(raw, str) else raw
        return OutfitResponse(
            outfits=data.get("outfits", []),
            occasion=data.get("occasion", req.occasion),
            weather=data.get("weather", req.weather),
            temperature=data.get("temperature", req.temperature),
        )
    except Exception as exc:
        logger.error("Outfit error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Outfit generation error: {exc}")


@app.post("/packing", tags=["AI"])
async def packing(req: PackingRequest) -> JSONResponse:
    """
    Generate a travel packing list.

    The agent orchestrates the full pipeline:
      1. get_weather_summary(destination, dates)
      2. generate_trip_packing_list(destination, dates, purpose, closet, weather)

    Returns the full PackingResult JSON.
    """
    agent = _require_agent()

    closet_summary = (
        f"\n\nUser's closet ({len(req.closet_items)} items): "
        + json.dumps(req.closet_items)
        if req.closet_items
        else "\n\nUser has no closet items saved yet."
    )

    message = (
        f"Generate a complete packing list for my trip to {req.destination} "
        f"from {req.start_date} to {req.end_date}. "
        f"Trip purpose: {req.purpose}."
        f"{closet_summary}"
        "\n\nFirst get the weather summary, then generate the packing list. "
        "Return the full packing list JSON."
    )

    try:
        reply = await agent.chat(message)
        return JSONResponse(content={"result": reply})
    except Exception as exc:
        logger.error("Packing error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Packing error: {exc}")


@app.post("/vision/analyze", tags=["AI"])
async def vision_analyze(
    file: UploadFile = File(..., description="Clothing item image (JPEG/PNG/WebP, max 10 MB)"),
) -> JSONResponse:
    """
    Analyse a garment image with GPT-4o Vision.
    Upload the image as multipart/form-data with field name 'file'.

    Returns structured garment attributes: type, fabric, colour, pattern,
    season, occasions, care instructions, eco score, and confidence.
    """
    agent = _require_agent()

    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic"}
    content_type = file.content_type or "image/jpeg"
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{content_type}'. Use JPEG, PNG, WebP, or HEIC.",
        )

    # Validate size (10 MB)
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")

    # Find the vision tool
    vision_tool = next(
        (t for t in agent._tools if "analyze_garment" in t.name),
        None,
    )
    if not vision_tool:
        raise HTTPException(status_code=503, detail="Vision tool not available")

    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        raw = await vision_tool.ainvoke({
            "image_base64": image_b64,
            "media_type": content_type,
        })
        data = json.loads(raw) if isinstance(raw, str) else raw
        return JSONResponse(content=data)
    except Exception as exc:
        logger.error("Vision error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vision analysis error: {exc}")


# ── Error handlers ────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        "Starting CLOZEHIVE AI Gateway on %s:%d",
        settings.gateway_host,
        settings.gateway_port,
    )
    uvicorn.run(
        "gateway:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        reload=False,
        log_level="info",
    )
