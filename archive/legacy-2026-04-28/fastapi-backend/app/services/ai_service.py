"""
AI integration service.

Connects to the existing Python AI service (LangChain / OpenAI) via HTTP.
Falls back to a direct ChatOpenAI call when the remote service is unavailable.

LangChain 1.x compatible — uses langchain_core + langchain_openai only.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

import httpx
from fastapi import HTTPException, status
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.config import settings
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    OutfitRequest,
    OutfitResponse,
    TravelPackRequest,
    TravelPackResponse,
)

logger = logging.getLogger("clozehive.ai")

# ── HTTP client for existing AI service ──────────────────────────────────────
_http: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            base_url=settings.AI_SERVICE_URL,
            timeout=httpx.Timeout(60.0),
        )
    return _http


async def close_http_client() -> None:
    global _http
    if _http and not _http.is_closed:
        await _http.aclose()


# ── Shared LLM factory ────────────────────────────────────────────────────────

def _make_llm(temperature: float = 0.7, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=temperature,
        streaming=streaming,
        api_key=settings.OPENAI_API_KEY,
    )


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that GPT sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop first line (```json or ```) and last line (```)
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return text.strip()


# ── AI Service ────────────────────────────────────────────────────────────────

class AIService:

    # ── Outfit ────────────────────────────────────────────────────────────────

    @staticmethod
    async def generate_outfit(request: OutfitRequest) -> OutfitResponse:
        client = get_http_client()
        try:
            resp = await client.post("/generate-outfit", json=request.model_dump())
            resp.raise_for_status()
            return AIService._normalise_outfit(resp.json())
        except httpx.HTTPError as exc:
            logger.warning("AI service unavailable (%s) — using LangChain fallback.", exc)
            return await AIService._outfit_fallback(request)

    @staticmethod
    async def _outfit_fallback(request: OutfitRequest) -> OutfitResponse:
        llm = _make_llm(temperature=0.7)

        closet_ctx = ""
        if request.closet_items:
            items_str = ", ".join(
                f"{i.get('name', 'item')} ({i.get('category', 'unknown')})"
                for i in request.closet_items[:20]
            )
            closet_ctx = f"\n\nAvailable wardrobe items: {items_str}"

        prompt = (
            f"Create 3 outfit suggestions for: {request.occasion}. "
            f"Weather: {request.weather or 'not specified'}. "
            f"Style preferences: {request.preferences or 'none'}.{closet_ctx}\n\n"
            "Return ONLY a valid JSON object — no explanation, no markdown fences:\n"
            '{"outfits": [{"name": "...", "items": [{"name": "...", "category": "...", '
            '"why": "..."}], "style_notes": "..."}], '
            '"explanation": "...", "missing_items": ["..."]}'
        )

        try:
            result = await llm.ainvoke([HumanMessage(content=prompt)])
            data = json.loads(_strip_code_fences(result.content))
            return AIService._normalise_outfit(data)
        except Exception as exc:
            logger.error("Outfit LangChain fallback failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service temporarily unavailable",
            )

    @staticmethod
    def _normalise_outfit(data: dict) -> OutfitResponse:
        from app.schemas.ai import OutfitItem, OutfitSuggestion

        outfits = []
        for o in data.get("outfits", []):
            raw_items = o.get("items", [])
            items = []
            for item in raw_items:
                if isinstance(item, dict):
                    items.append(OutfitItem(
                        name=item.get("name", ""),
                        category=item.get("category", "unknown"),
                        color=item.get("color"),
                        why=item.get("why"),
                    ))
                else:
                    items.append(OutfitItem(name=str(item), category="unknown"))
            outfits.append(OutfitSuggestion(
                name=o.get("name", "Outfit"),
                items=items,
                style_notes=o.get("style_notes"),
            ))

        return OutfitResponse(
            outfits=outfits,
            explanation=data.get("explanation", ""),
            missing_items=data.get("missing_items", []),
        )

    # ── Outfit SSE stream ─────────────────────────────────────────────────────

    @staticmethod
    async def stream_outfit(request: OutfitRequest) -> AsyncIterator[str]:
        """
        Proxy SSE from existing AI service; fall back to a single-event JSON stream.
        """
        client = get_http_client()
        try:
            async with client.stream(
                "POST",
                "/outfit/stream",
                json=request.model_dump(),
                timeout=httpx.Timeout(120.0),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield line + "\n"
            yield 'data: {"type": "done"}\n\n'
        except httpx.HTTPError:
            # Fallback: generate synchronously, wrap as a single result event
            try:
                result = await AIService._outfit_fallback(request)
                yield f"data: {json.dumps({'type': 'result', 'data': result.model_dump()})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            yield 'data: {"type": "done"}\n\n'

    # ── Travel Packing ────────────────────────────────────────────────────────

    @staticmethod
    async def generate_packing_list(request: TravelPackRequest) -> TravelPackResponse:
        client = get_http_client()
        try:
            resp = await client.post("/generate-packing-list", json=request.model_dump())
            resp.raise_for_status()
            return AIService._normalise_packing(resp.json(), request)
        except httpx.HTTPError as exc:
            logger.warning("AI service unavailable (%s) — using LangChain fallback.", exc)
            return await AIService._packing_fallback(request)

    @staticmethod
    async def _packing_fallback(request: TravelPackRequest) -> TravelPackResponse:
        llm = _make_llm(temperature=0.5)
        activities = ", ".join(request.activities or ["general tourism"])
        prompt = (
            f"Create a complete packing list for a {request.duration_days}-day trip to "
            f"{request.destination}. Activities: {activities}. "
            f"Weather: {request.weather or 'unknown'}.\n\n"
            "Return ONLY valid JSON — no markdown fences:\n"
            '{"packing_list": [{"category": "Clothing", "items": ["item1", "item2"]}, '
            '{"category": "Toiletries", "items": [...]}], '
            '"ai_tips": "short practical tip"}'
        )
        try:
            result = await llm.ainvoke([HumanMessage(content=prompt)])
            data = json.loads(_strip_code_fences(result.content))
            return AIService._normalise_packing(data, request)
        except Exception as exc:
            logger.error("Packing LangChain fallback failed: %s", exc)
            raise HTTPException(status_code=503, detail="AI service temporarily unavailable")

    @staticmethod
    def _normalise_packing(data: dict, request: TravelPackRequest) -> TravelPackResponse:
        from app.schemas.ai import PackingCategory

        packing_list = [
            PackingCategory(
                category=cat.get("category", "General"),
                items=cat.get("items", []),
            )
            for cat in data.get("packing_list", [])
        ]
        return TravelPackResponse(
            destination=request.destination,
            duration_days=request.duration_days,
            packing_list=packing_list,
            ai_tips=data.get("ai_tips", ""),
            total_items=sum(len(c.items) for c in packing_list),
        )

    # ── Chat ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def chat(request: ChatRequest) -> ChatResponse:
        client = get_http_client()
        try:
            resp = await client.post("/chat", json=request.model_dump())
            resp.raise_for_status()
            data = resp.json()
            return ChatResponse(
                response=data.get("response", ""),
                session_id=data.get("session_id"),
            )
        except httpx.HTTPError:
            return await AIService._chat_fallback(request)

    @staticmethod
    async def _chat_fallback(request: ChatRequest) -> ChatResponse:
        llm = _make_llm(temperature=0.8)

        messages = [
            SystemMessage(content=(
                "You are CLOZEHIVE, an expert AI fashion stylist and personal wardrobe assistant. "
                "Help users with outfit advice, wardrobe organisation, and style tips. "
                "Be friendly, specific, and practical."
            ))
        ]

        # Last 10 history messages to stay within token limits
        for m in request.history[-10:]:
            if m.role == "user":
                messages.append(HumanMessage(content=m.content))
            else:
                messages.append(AIMessage(content=m.content))

        messages.append(HumanMessage(content=request.message))

        try:
            result = await llm.ainvoke(messages)
            return ChatResponse(response=result.content)
        except Exception as exc:
            logger.error("Chat LangChain fallback failed: %s", exc)
            raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
