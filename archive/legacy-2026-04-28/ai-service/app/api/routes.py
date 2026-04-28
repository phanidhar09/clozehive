import json
import re

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import settings
from app.models.schemas import (
    OutfitRequest, OutfitResponse,
    PackingRequest, PackingResponse,
    ChatRequest, ChatResponse,
    VisionAnalysisResponse,
    OutfitAnalysisResponse,
)
from app.services.vision_service import analyse_image, analyse_outfit_image
from app.services.outfit_service import generate_outfits
from app.services.packing_service import generate_packing_list

router = APIRouter()


# ── Vision ─────────────────────────────────────────────────
@router.post("/vision/analyze", response_model=VisionAnalysisResponse, tags=["Vision"])
async def vision_analyze(image: UploadFile = File(...)):
    """
    Analyse an uploaded clothing image with GPT-4o Vision.

    Returns structured garment attributes:
    garment_type, fabric, color, pattern, season, occasion,
    care_instructions, wearing_tips, eco_score.
    """
    allowed = {"image/jpeg", "image/png", "image/webp", "image/heic"}
    content_type = image.content_type or "image/jpeg"
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {content_type}")

    data = await image.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

    result = analyse_image(data, content_type)
    return result


# ── Vision: outfit photo ────────────────────────────────────
@router.post("/vision/analyze-outfit", response_model=OutfitAnalysisResponse, tags=["Vision"])
async def vision_analyze_outfit(image: UploadFile = File(...)):
    """
    Analyse a full-body / outfit photo with GPT-4o Vision.

    Detects every clothing item the person is wearing and returns them as
    individual items ready to be added to the wardrobe. Also removes the
    background from the uploaded photo.
    """
    allowed = {"image/jpeg", "image/png", "image/webp", "image/heic"}
    content_type = image.content_type or "image/jpeg"
    if content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {content_type}")

    data = await image.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 10 MB)")

    result = analyse_outfit_image(data, content_type)
    return result


# ── Outfit ─────────────────────────────────────────────────
@router.post("/outfit/generate", response_model=OutfitResponse, tags=["Outfit"])
async def outfit_generate(req: OutfitRequest):
    """
    Generate top-3 outfit combinations from the user's closet.

    Input: closet_items list + occasion + weather + temperature.
    Output: ranked outfit suggestions with explanations.
    """
    if not req.closet_items:
        raise HTTPException(status_code=400, detail="closet_items cannot be empty")

    result = generate_outfits(
        closet_items=req.closet_items,
        occasion=req.occasion,
        weather=req.weather,
        temperature=req.temperature,
    )
    return result


# ── Packing ────────────────────────────────────────────────
@router.post("/packing/generate", response_model=PackingResponse, tags=["Packing"])
async def packing_generate(req: PackingRequest):
    """
    Generate a smart packing list for a trip.

    Steps:
    1. Fetch mock weather per day for the destination.
    2. Determine required clothing categories based on weather + purpose.
    3. Compare required items with user's closet → find missing items.
    4. Build a daily outfit plan.
    5. Return packing list, missing items, alerts, daily plan.
    """
    try:
        result = generate_packing_list(
            destination=req.destination,
            start_date=req.start_date,
            end_date=req.end_date,
            purpose=req.purpose,
            closet_items=req.closet_items,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Chat ───────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(req: ChatRequest):
    """Simple wardrobe-aware chat endpoint."""
    from openai import OpenAI

    if not settings.openai_api_key:
        return ChatResponse(
            reply="Hi! I'm your wardrobe assistant. AI is not configured yet, but I can see your closet has items ready to style.",
            suggestions=["Try generating an outfit for today", "Plan your next trip with the packing agent"],
        )

    client = OpenAI(api_key=settings.openai_api_key)
    closet_summary = "\n".join(
        f"- {i.get('name', 'Item')} ({i.get('category', '?')})" for i in (req.closet_items or [])[:15]
    )
    system = (
        "You are ClozéHive, an AI wardrobe assistant. "
        "Answer wardrobe, fashion, and outfit questions concisely. "
        f"User's closet:\n{closet_summary or 'Empty closet'}"
    )
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": req.message}],
            max_tokens=400,
            temperature=0.7,
        )
        return ChatResponse(reply=resp.choices[0].message.content, suggestions=[])
    except Exception as e:
        return ChatResponse(reply=f"Sorry, I ran into an issue: {str(e)}", suggestions=[])


# ══════════════════════════════════════════════════════════════
#  STREAMING ENDPOINTS  (text/event-stream)
#  Event format:  data: {"type": "token"|"status"|"result"|"error"|"done", ...}\n\n
# ══════════════════════════════════════════════════════════════

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ── /chat/stream ────────────────────────────────────────────
@router.post("/chat/stream", tags=["Chat"])
async def chat_stream(req: ChatRequest):
    """Token-by-token streaming chat via SSE."""

    def generate():
        if not settings.openai_api_key:
            fallback = (
                "Hi! I'm your ClozéHive wardrobe assistant. "
                "The AI service isn't configured yet — add your OPENAI_API_KEY to get personalised styling advice."
            )
            for word in fallback.split(" "):
                yield _sse({"type": "token", "content": word + " "})
            yield _sse({"type": "done"})
            return

        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        closet_summary = "\n".join(
            f"- {i.get('name', 'Item')} ({i.get('category', '?')})"
            for i in (req.closet_items or [])[:20]
        )
        system = (
            "You are ClozéHive, a friendly and knowledgeable AI wardrobe assistant. "
            "Give concise, practical styling advice. Reference specific items from the user's closet when relevant.\n"
            f"User's wardrobe ({len(req.closet_items or [])} items):\n"
            f"{closet_summary or '(empty closet)'}"
        )
        try:
            stream = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": req.message},
                ],
                max_tokens=500,
                temperature=0.7,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield _sse({"type": "token", "content": delta.content})
            yield _sse({"type": "done"})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# ── /outfit/stream ──────────────────────────────────────────
@router.post("/outfit/stream", tags=["Outfit"])
async def outfit_stream(req: OutfitRequest):
    """Generate outfits with live status updates via SSE."""

    def generate():
        if not req.closet_items:
            yield _sse({"type": "error", "message": "No closet items provided"})
            return

        from app.services.outfit_service import (
            _build_closet_summary, OUTFIT_PROMPT, _mock_outfit_response,
        )
        from app.models.schemas import OutfitSuggestion, OutfitResponse

        yield _sse({"type": "status", "message": "Analysing your wardrobe…"})

        if not settings.openai_api_key:
            result = _mock_outfit_response(
                req.closet_items, req.occasion, req.weather, req.temperature
            )
            yield _sse({"type": "result", "data": result.model_dump()})
            yield _sse({"type": "done"})
            return

        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        closet_summary = _build_closet_summary(req.closet_items)
        prompt = OUTFIT_PROMPT.format(
            closet=closet_summary,
            occasion=req.occasion,
            weather=req.weather,
            temperature=req.temperature,
        )

        yield _sse({"type": "status", "message": f"Curating outfit combinations for {req.occasion}…"})

        try:
            stream = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.7,
                stream=True,
            )
            full_response = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_response += delta.content

            yield _sse({"type": "status", "message": "Finalising outfit suggestions…"})

            raw = re.sub(r"```(?:json)?", "", full_response).strip()
            data = json.loads(raw)

            item_map = {i.id: i for i in req.closet_items}
            suggestions = []
            for o in data.get("outfits", []):
                matched = [item_map[iid].model_dump() for iid in o.get("item_ids", []) if iid in item_map]
                suggestions.append(
                    OutfitSuggestion(
                        name=o.get("name", "Outfit"),
                        item_ids=[iid for iid in o.get("item_ids", []) if iid in item_map],
                        items=matched,
                        explanation=o.get("explanation", ""),
                        style_score=float(o.get("style_score", 7.5)),
                        occasion_fit=o.get("occasion_fit", ""),
                        weather_fit=o.get("weather_fit", ""),
                    )
                )
            result = OutfitResponse(
                outfits=suggestions,
                occasion=req.occasion,
                weather=req.weather,
                temperature=req.temperature,
            )
            yield _sse({"type": "result", "data": result.model_dump()})
        except Exception as exc:
            print(f"[OutfitStream] Error: {exc} — falling back to mock")
            result = _mock_outfit_response(
                req.closet_items, req.occasion, req.weather, req.temperature
            )
            yield _sse({"type": "result", "data": result.model_dump()})

        yield _sse({"type": "done"})

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# ── /packing/stream ─────────────────────────────────────────
@router.post("/packing/stream", tags=["Packing"])
async def packing_stream(req: PackingRequest):
    """Generate packing list with live status + streaming AI tips via SSE."""

    def generate():
        try:
            from app.services.weather_service import fetch_weather, summarise_weather
            from app.services.packing_service import (
                _required_categories, _match_closet, _build_daily_plan,
                _build_alerts, PACKING_AI_PROMPT, _get_client,
            )
            from app.models.schemas import PackingResponse

            yield _sse({"type": "status", "message": f"Fetching weather data for {req.destination}…"})
            weather_days = fetch_weather(req.destination, req.start_date, req.end_date)
            weather_summary = summarise_weather(weather_days)
            duration = len(weather_days)

            yield _sse({"type": "status", "message": "Matching wardrobe to trip requirements…"})
            required = _required_categories(weather_days, req.purpose)
            packing, missing = _match_closet(required, req.closet_items)
            daily_plan = _build_daily_plan(weather_days, req.closet_items, req.purpose)
            alerts = _build_alerts(missing, weather_summary, duration)

            # Stream AI enrichment token-by-token (this IS readable prose)
            if settings.openai_api_key:
                yield _sse({"type": "status", "message": "Generating AI packing insights…"})
                from openai import OpenAI

                client = OpenAI(api_key=settings.openai_api_key)
                closet_summary_str = "\n".join(
                    f"- {i.name} ({i.category})" for i in req.closet_items[:20]
                )
                packing_list_str = "\n".join(f"- {p.name}" for p in packing)
                missing_str = "\n".join(f"- {m.name}: {m.reason}" for m in missing) or "None"

                prompt = PACKING_AI_PROMPT.format(
                    destination=req.destination,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    duration=duration,
                    purpose=req.purpose,
                    weather_summary=json.dumps(weather_summary),
                    closet_count=len(req.closet_items),
                    closet_summary=closet_summary_str,
                    packing_list=packing_list_str,
                    missing_list=missing_str,
                )
                try:
                    stream = client.chat.completions.create(
                        model=settings.openai_model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=400,
                        temperature=0.5,
                        stream=True,
                    )
                    full_ai = ""
                    for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            full_ai += delta.content
                            yield _sse({"type": "token", "content": delta.content})

                    raw = re.sub(r"```(?:json)?", "", full_ai).strip()
                    ai_extra = json.loads(raw)
                    if ai_extra.get("summary"):
                        alerts.insert(0, f"💡  {ai_extra['summary']}")
                    for tip in ai_extra.get("extra_tips", []):
                        alerts.append(f"📌  {tip}")
                except Exception as exc:
                    print(f"[PackingStream] AI enrichment failed: {exc}")

            packing_ids = [p.closet_item_id for p in packing if p.closet_item_id]
            result = PackingResponse(
                destination=req.destination,
                start_date=req.start_date,
                end_date=req.end_date,
                duration_days=duration,
                trip_type=req.purpose,
                weather_summary=weather_summary,
                packing_list=packing,
                missing_items=missing,
                daily_plan=daily_plan,
                alerts=alerts,
                packing_item_ids=packing_ids,
            )
            yield _sse({"type": "result", "data": result.model_dump()})

        except ValueError as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

        yield _sse({"type": "done"})

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)
