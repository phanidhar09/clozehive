"""
Outfit recommendation service.
Uses GPT-4o to reason over the user's closet and suggest top-3 outfits.
"""
import json
import re
from openai import OpenAI
from app.core.config import settings
from app.models.schemas import ClosetItem, OutfitSuggestion, OutfitResponse

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _build_closet_summary(items: list[ClosetItem]) -> str:
    lines = []
    for i in items:
        occ = ", ".join(i.occasion) if i.occasion else "general"
        lines.append(
            f"- ID:{i.id} | {i.name} | {i.category} | color:{i.color or '?'} | "
            f"fabric:{i.fabric or '?'} | season:{i.season or '?'} | occasion:{occ}"
        )
    return "\n".join(lines)


OUTFIT_PROMPT = """
You are a professional personal stylist AI.

User's closet:
{closet}

Request:
- Occasion: {occasion}
- Weather: {weather}
- Temperature: {temperature}°C

Create the top 3 outfit combinations from the closet items above.
Respond ONLY with valid JSON matching this schema:

{{
  "outfits": [
    {{
      "name": "<outfit name>",
      "item_ids": ["<item id>", "<item id>"],
      "explanation": "<why this outfit works>",
      "style_score": <float 1-10>,
      "occasion_fit": "<how well it fits the occasion>",
      "weather_fit": "<how well it suits the weather>"
    }}
  ]
}}

Rules:
- Only use item IDs from the provided closet list
- Each outfit must have 2-4 items (top + bottom minimum)
- Explain colour harmony and occasion suitability
- Return ONLY valid JSON, no markdown
"""


def generate_outfits(
    closet_items: list[ClosetItem],
    occasion: str,
    weather: str,
    temperature: float,
) -> OutfitResponse:
    if not closet_items:
        return OutfitResponse(outfits=[], occasion=occasion, weather=weather, temperature=temperature)

    closet_summary = _build_closet_summary(closet_items)
    prompt = OUTFIT_PROMPT.format(
        closet=closet_summary, occasion=occasion, weather=weather, temperature=temperature
    )

    if not settings.openai_api_key:
        return _mock_outfit_response(closet_items, occasion, weather, temperature)

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.7,
        )
        raw = response.choices[0].message.content
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        data = json.loads(raw)

        item_map = {i.id: i for i in closet_items}
        suggestions = []
        for o in data.get("outfits", []):
            matched_items = [item_map[iid].model_dump() for iid in o.get("item_ids", []) if iid in item_map]
            suggestions.append(OutfitSuggestion(
                name=o.get("name", "Outfit"),
                item_ids=[iid for iid in o.get("item_ids", []) if iid in item_map],
                items=matched_items,
                explanation=o.get("explanation", ""),
                style_score=float(o.get("style_score", 7.5)),
                occasion_fit=o.get("occasion_fit", ""),
                weather_fit=o.get("weather_fit", ""),
            ))
        return OutfitResponse(outfits=suggestions, occasion=occasion, weather=weather, temperature=temperature)

    except Exception as e:
        print(f"[OutfitService] Error: {e}")
        return _mock_outfit_response(closet_items, occasion, weather, temperature)


def _mock_outfit_response(
    closet_items: list[ClosetItem], occasion: str, weather: str, temperature: float
) -> OutfitResponse:
    tops = [i for i in closet_items if i.category in ("tops", "shirts", "blouses")]
    bottoms = [i for i in closet_items if i.category in ("bottoms", "pants", "skirts", "jeans")]
    shoes = [i for i in closet_items if i.category == "shoes"]
    outerwear = [i for i in closet_items if i.category in ("jackets", "outerwear")]

    outfits = []
    used_combos: set[frozenset] = set()

    for i, top in enumerate(tops[:3]):
        bottom = bottoms[i % len(bottoms)] if bottoms else None
        shoe = shoes[i % len(shoes)] if shoes else None
        jacket = outerwear[0] if (temperature < 18 and outerwear) else None

        ids = [top.id]
        items = [top.model_dump()]
        if bottom:
            ids.append(bottom.id)
            items.append(bottom.model_dump())
        if shoe:
            ids.append(shoe.id)
            items.append(shoe.model_dump())
        if jacket:
            ids.append(jacket.id)
            items.append(jacket.model_dump())

        combo = frozenset(ids)
        if combo in used_combos:
            continue
        used_combos.add(combo)

        outfits.append(OutfitSuggestion(
            name=f"Outfit {i + 1} — {occasion.capitalize()}",
            item_ids=ids,
            items=items,
            explanation=f"A {occasion} outfit combining {top.color or ''} {top.name} with {bottom.name if bottom else 'matching bottom'}. Suitable for {weather} weather at {temperature}°C.",
            style_score=round(7.5 + i * 0.3, 1),
            occasion_fit=f"Good fit for {occasion}",
            weather_fit=f"Suitable for {weather} at {temperature}°C",
        ))
        if len(outfits) == 3:
            break

    return OutfitResponse(outfits=outfits, occasion=occasion, weather=weather, temperature=temperature)
