"""Location intelligence — curated dress-norm / climate profiles for destinations.

Provides a prompt-ready "location context" block used by both the travel packing
planner and the daily-outfit engine. Curated profiles give deterministic, high
quality guidance for top destinations; everywhere else the block instructs the
model to infer local norms from its own knowledge (the hybrid fallback).

``build_location_context_block_async`` (Phase 2 of the web-intelligence roadmap)
adds a middle tier for non-curated destinations: live dress-guideline guidance
fetched via Tavily and cached for 30 days per destination. Resolution order is
static-first, search-second, LLM-infer last:

  curated profile  >  live web guidance (Tavily)  >  LLM-infer fallback

The curated key set and fuzzy-match logic deliberately mirror
``weather_service._profile`` so weather and location data line up for the same
destinations.
"""

from __future__ import annotations

from typing import Any, Literal

from app.core import web_intelligence

Mode = Literal["travel", "daily"]

# Live dress guidelines are stable — a city's norms don't shift week to week.
DRESS_GUIDELINES_TTL_S = 30 * 24 * 3600

# ── Curated location profiles ─────────────────────────────────────────────────
# modesty: relaxed | moderate | conservative
# Keys are lowercased; matched by exact key or "first token of input in key".
_LOCATION_PROFILES: dict[str, dict[str, Any]] = {
    "dubai": {
        "climate_type": "Hot desert — very hot summers, warm winters",
        "seasonal_note": "Brutal heat May–Sep; pleasant Nov–Mar.",
        "modesty": "conservative",
        "formality_baseline": "smart, polished; flashy is welcome",
        "cultural_notes": "Cover shoulders and knees in malls, souks, and government buildings; "
        "modest dress required at mosques (women cover hair). Beaches/pools/clubs are relaxed.",
        "local_vibe": "Glam, label-conscious, breathable luxury.",
        "fabric_tips": "Lightweight linen, cotton, and flowing fabrics; sunglasses and a sun hat.",
        "avoid": "Sheer, very short, or revealing clothing in public/religious areas.",
    },
    "abu dhabi": {
        "climate_type": "Hot desert",
        "seasonal_note": "Extreme heat in summer; mild winters.",
        "modesty": "conservative",
        "formality_baseline": "smart and modest",
        "cultural_notes": "Sheikh Zayed Mosque requires full cover (ankles, wrists, hair for women).",
        "local_vibe": "Refined, modest-luxe.",
        "fabric_tips": "Breathable linen/cotton, a scarf for cover-ups.",
        "avoid": "Beachwear or short hems away from resorts.",
    },
    "doha": {
        "climate_type": "Hot desert",
        "seasonal_note": "Searing summers; pleasant winters.",
        "modesty": "conservative",
        "formality_baseline": "modest and neat",
        "cultural_notes": "Shoulders and knees covered in public; modest dress at the Souq and mosques.",
        "local_vibe": "Modern-modest.",
        "fabric_tips": "Lightweight breathable layers, a light scarf.",
        "avoid": "Tight or revealing outfits in public.",
    },
    "cairo": {
        "climate_type": "Hot desert",
        "seasonal_note": "Hot days, cooler desert nights.",
        "modesty": "conservative",
        "formality_baseline": "modest casual",
        "cultural_notes": "Modest dress respected, especially at mosques and outside tourist resorts.",
        "local_vibe": "Practical and modest.",
        "fabric_tips": "Loose cotton/linen, a scarf, comfortable closed shoes for ruins.",
        "avoid": "Shorts and bare shoulders at religious or rural sites.",
    },
    "marrakech": {
        "climate_type": "Semi-arid, hot",
        "seasonal_note": "Very hot summers; cool evenings year-round.",
        "modesty": "conservative",
        "formality_baseline": "modest, colourful casual",
        "cultural_notes": "Cover shoulders and knees in the medina and souks; modest dress shows respect.",
        "local_vibe": "Boho, earthy, layered.",
        "fabric_tips": "Loose linen/cotton, a light scarf, sturdy sandals.",
        "avoid": "Short shorts and crop tops in the medina.",
    },
    "istanbul": {
        "climate_type": "Temperate, warm summers",
        "seasonal_note": "Hot summers, cool damp winters.",
        "modesty": "moderate",
        "formality_baseline": "smart casual, fashion-forward",
        "cultural_notes": "Mosques require covered shoulders/knees and a headscarf for women; "
        "city life is stylish and relatively relaxed.",
        "local_vibe": "Chic European-meets-Levantine.",
        "fabric_tips": "Layers plus a scarf that doubles as mosque cover.",
        "avoid": "Beachwear away from the coast.",
    },
    "bangkok": {
        "climate_type": "Tropical — hot and humid",
        "seasonal_note": "Humid year-round; monsoon rains May–Oct.",
        "modesty": "moderate",
        "formality_baseline": "light and casual",
        "cultural_notes": "Temples (Grand Palace, Wat Pho) require covered shoulders and knees — "
        "carry a sarong/scarf. Street and mall wear is relaxed.",
        "local_vibe": "Breezy, colourful streetwear.",
        "fabric_tips": "Quick-dry, breathable fabrics; a foldable rain layer.",
        "avoid": "Sleeveless tops and short shorts at temples.",
    },
    "mumbai": {
        "climate_type": "Tropical — hot, humid coastal",
        "seasonal_note": "Heavy monsoon Jun–Sep; humid most of the year.",
        "modesty": "moderate",
        "formality_baseline": "smart casual, vibrant",
        "cultural_notes": "Cosmopolitan and fairly relaxed, but cover up at temples and in older "
        "neighbourhoods; modest dress is appreciated at religious sites.",
        "local_vibe": "Bright, expressive, fusion of traditional and Western.",
        "fabric_tips": "Breathable cottons; a sturdy umbrella in monsoon season.",
        "avoid": "Very revealing outfits at temples and conservative areas.",
    },
    "delhi": {
        "climate_type": "Humid subtropical — hot summers, cool winters",
        "seasonal_note": "Scorching May–Jun, chilly Dec–Jan, monsoon Jul–Sep.",
        "modesty": "conservative",
        "formality_baseline": "modest smart casual",
        "cultural_notes": "Modest dress recommended; cover shoulders/knees at temples, mosques, "
        "and gurdwaras (head covering required at gurdwaras).",
        "local_vibe": "Traditional-meets-contemporary, layered in winter.",
        "fabric_tips": "Cotton for heat, layers for winter, a scarf/dupatta for cover.",
        "avoid": "Short or tight clothing at religious sites.",
    },
    "hyderabad": {
        "climate_type": "Hot semi-arid",
        "seasonal_note": "Hot summers, pleasant winters, modest monsoon.",
        "modesty": "moderate",
        "formality_baseline": "smart casual",
        "cultural_notes": "Cover up at Charminar, mosques, and temples; modest dress respected "
        "in the old city.",
        "local_vibe": "Heritage-rich, modest-modern blend.",
        "fabric_tips": "Breathable cottons, a light scarf.",
        "avoid": "Revealing outfits in the old city and religious sites.",
    },
    "varanasi": {
        "climate_type": "Humid subtropical",
        "seasonal_note": "Very hot summers; pleasant winters.",
        "modesty": "conservative",
        "formality_baseline": "modest, simple",
        "cultural_notes": "Sacred city — dress conservatively at ghats and temples; cover shoulders "
        "and knees.",
        "local_vibe": "Spiritual, understated.",
        "fabric_tips": "Loose cotton, a scarf, slip-on shoes for temple visits.",
        "avoid": "Shorts, tank tops, and bold revealing wear.",
    },
    "singapore": {
        "climate_type": "Tropical rainforest — hot, humid, rainy",
        "seasonal_note": "Hot and humid all year with frequent showers.",
        "modesty": "relaxed",
        "formality_baseline": "smart casual; AC venues run cold",
        "cultural_notes": "Relaxed dress overall; cover up at temples and mosques.",
        "local_vibe": "Polished, modern, fuss-free.",
        "fabric_tips": "Light breathable layers plus a thin layer for strong air-conditioning.",
        "avoid": "Heavy fabrics; pack a compact umbrella.",
    },
    "bali": {
        "climate_type": "Tropical — warm and humid",
        "seasonal_note": "Dry Apr–Oct, wet Nov–Mar.",
        "modesty": "moderate",
        "formality_baseline": "relaxed resort/beachwear",
        "cultural_notes": "Temples require a sarong and sash (often provided) and covered shoulders. "
        "Beach clubs and resorts are very relaxed.",
        "local_vibe": "Boho beach, flowy and natural.",
        "fabric_tips": "Light linen/cotton, swimwear, a sarong that doubles as temple cover.",
        "avoid": "Swimwear away from the beach; uncovered legs at temples.",
    },
    "miami": {
        "climate_type": "Tropical monsoon — hot, humid",
        "seasonal_note": "Hot and humid; rainy/hurricane season Jun–Nov.",
        "modesty": "relaxed",
        "formality_baseline": "vibrant resort and beachwear",
        "cultural_notes": "Very relaxed, show-skin-friendly; nightlife leans glamorous.",
        "local_vibe": "Bold, colourful, beach-glam.",
        "fabric_tips": "Breathable, bright pieces; swimwear and cover-ups.",
        "avoid": "Heavy/dark layers.",
    },
    "london": {
        "climate_type": "Temperate maritime — mild, wet",
        "seasonal_note": "Cool and rainy year-round; layered most months.",
        "modesty": "relaxed",
        "formality_baseline": "smart casual, polished",
        "cultural_notes": "No dress restrictions; weather drives the wardrobe.",
        "local_vibe": "Refined, layered, neutral-forward with edge.",
        "fabric_tips": "Waterproof outer layer, versatile layers, comfortable walking shoes.",
        "avoid": "Relying on a single light layer — pack for rain and chill.",
    },
    "paris": {
        "climate_type": "Temperate — mild, variable",
        "seasonal_note": "Cool springs/autumns, warm summers, chilly winters.",
        "modesty": "relaxed",
        "formality_baseline": "elevated smart casual",
        "cultural_notes": "Notre-Dame/Sacré-Cœur and churches prefer covered shoulders.",
        "local_vibe": "Effortless chic — tailored, neutral, quality basics.",
        "fabric_tips": "Layerable knits, a trench, leather shoes; a scarf is essential.",
        "avoid": "Athleisure/sneakers-everywhere looks if you want to blend in.",
    },
    "amsterdam": {
        "climate_type": "Temperate maritime — cool, wet, windy",
        "seasonal_note": "Frequent rain and wind; cold winters.",
        "modesty": "relaxed",
        "formality_baseline": "casual, practical",
        "cultural_notes": "Relaxed; cycling-friendly practical dressing dominates.",
        "local_vibe": "Understated, functional, minimal.",
        "fabric_tips": "Windproof/waterproof jacket, layers, flat comfortable shoes for biking.",
        "avoid": "Heels on cobblestones; flimsy umbrellas in the wind.",
    },
    "rome": {
        "climate_type": "Mediterranean — warm, dry summers",
        "seasonal_note": "Hot summers, mild wet winters.",
        "modesty": "moderate",
        "formality_baseline": "smart, put-together",
        "cultural_notes": "St. Peter's and churches strictly require covered shoulders and knees.",
        "local_vibe": "Elegant Mediterranean — tailored and sun-ready.",
        "fabric_tips": "Linen/cotton, a light scarf or shawl for churches, comfy walking shoes.",
        "avoid": "Shorts and tank tops at the Vatican and churches.",
    },
    "barcelona": {
        "climate_type": "Mediterranean — warm",
        "seasonal_note": "Warm summers, mild winters.",
        "modesty": "relaxed",
        "formality_baseline": "casual chic",
        "cultural_notes": "Beach-relaxed, but cover up at the Sagrada Família and churches.",
        "local_vibe": "Sunny, stylish-casual.",
        "fabric_tips": "Light layers, swimwear plus a cover-up, walkable shoes.",
        "avoid": "Beachwear in the city centre and churches.",
    },
    "new york": {
        "climate_type": "Humid continental — four seasons",
        "seasonal_note": "Hot humid summers, cold snowy winters.",
        "modesty": "relaxed",
        "formality_baseline": "polished urban",
        "cultural_notes": "Anything goes; season dictates layers.",
        "local_vibe": "Sleek, dark-neutral, fast-paced.",
        "fabric_tips": "Season-appropriate layers; broken-in walking shoes; a warm coat in winter.",
        "avoid": "Under-packing outerwear in winter.",
    },
    "los angeles": {
        "climate_type": "Mediterranean — warm, dry",
        "seasonal_note": "Warm and dry most of the year; cool evenings.",
        "modesty": "relaxed",
        "formality_baseline": "casual, relaxed-cool",
        "cultural_notes": "Very casual; effortless dressing is the norm.",
        "local_vibe": "Laid-back, athleisure-friendly, sunny.",
        "fabric_tips": "Light layers plus one warmer layer for cool nights.",
        "avoid": "Overdressing — LA skews casual.",
    },
    "san francisco": {
        "climate_type": "Cool-summer Mediterranean — foggy, mild",
        "seasonal_note": "Cool and foggy year-round; little seasonal swing.",
        "modesty": "relaxed",
        "formality_baseline": "casual, tech-relaxed",
        "cultural_notes": "Relaxed; the famous chill and wind drive the wardrobe.",
        "local_vibe": "Layered casual, practical.",
        "fabric_tips": "Always pack a warm layer and a windproof jacket, even in summer.",
        "avoid": "Assuming 'California = hot' — SF is cool and windy.",
    },
    "chicago": {
        "climate_type": "Humid continental — windy",
        "seasonal_note": "Hot summers, very cold windy winters.",
        "modesty": "relaxed",
        "formality_baseline": "smart casual",
        "cultural_notes": "No restrictions; wind and cold drive layering.",
        "local_vibe": "Practical urban layered.",
        "fabric_tips": "Windproof outer layer, warm layers in winter.",
        "avoid": "Underestimating the wind chill.",
    },
    "tokyo": {
        "climate_type": "Humid subtropical — four seasons",
        "seasonal_note": "Hot humid summers, mild winters, rainy June.",
        "modesty": "moderate",
        "formality_baseline": "neat, considered, fashion-forward",
        "cultural_notes": "Shoulders often kept covered; tidy, understated dressing is valued. "
        "Slip-on-friendly shoes help (shoes off indoors at temples/homes).",
        "local_vibe": "Polished, minimal, detail-oriented street style.",
        "fabric_tips": "Layerable neat pieces, easy on/off shoes, a compact umbrella in June.",
        "avoid": "Overly revealing or sloppy outfits.",
    },
    "kyoto": {
        "climate_type": "Humid subtropical",
        "seasonal_note": "Hot humid summers, cold winters, beautiful spring/autumn.",
        "modesty": "moderate",
        "formality_baseline": "neat and modest",
        "cultural_notes": "Many temples and shrines — modest, tidy dress and easy-off shoes help.",
        "local_vibe": "Refined, traditional-respectful.",
        "fabric_tips": "Comfortable layers and walkable slip-on shoes.",
        "avoid": "Loud, revealing outfits at temples.",
    },
    "sydney": {
        "climate_type": "Temperate — warm summers, mild winters",
        "seasonal_note": "Seasons reversed (warm Dec–Feb); strong UV.",
        "modesty": "relaxed",
        "formality_baseline": "casual, beach-smart",
        "cultural_notes": "Very relaxed; sun protection matters more than coverage.",
        "local_vibe": "Easy coastal-casual.",
        "fabric_tips": "Breathable layers, swimwear, sun hat and sunglasses (high UV).",
        "avoid": "Forgetting sun protection.",
    },
}

_DEFAULT_KEY: str | None = None  # no curated default — fall back to LLM inference


def get_location_profile(name: str) -> dict[str, Any] | None:
    """Return the curated profile for a destination, or None if not curated.

    Matching mirrors ``weather_service._profile``: exact key first, then
    "first token of the input appears in a key".
    """
    if not name:
        return None
    key = name.strip().lower()
    if key in _LOCATION_PROFILES:
        return _LOCATION_PROFILES[key]
    first = key.split()[0] if key.split() else key
    for profile_key, value in _LOCATION_PROFILES.items():
        if first and first in profile_key:
            return value
    return None


def build_location_context_block(name: str, *, mode: Mode = "travel") -> str:
    """Return a prompt-ready location-context block for the destination.

    Curated destinations yield deterministic dress-norm guidance; everything
    else yields an instruction asking the model to infer local norms (the
    hybrid fallback). Returns "" only when ``name`` is empty.
    """
    if not name or not name.strip():
        return ""

    label = name.strip()
    profile = get_location_profile(label)

    if mode == "travel":
        header = "[DESTINATION LOCATION PREFERENCES]"
        constraint = (
            "Treat the local dress norms and modesty level as CONSTRAINTS when choosing "
            "wardrobe items: prefer pieces that respect them, suggest cover-ups or layers "
            "from the user's closet where coverage is needed (e.g. temples/mosques/conservative "
            "areas), and never recommend items that would violate local norms. Reflect the most "
            "important point in the trip_summary.location_etiquette field."
        )
    else:  # daily
        header = "[LOCAL CONTEXT]"
        constraint = (
            "Factor the local climate and everyday appropriateness for this place into the "
            "recommendation and its weather/style scoring. Favour items suited to the typical "
            "local conditions and dress sensibilities."
        )

    if profile:
        lines = [
            header,
            f"Location: {label}",
            f"Climate: {profile['climate_type']}",
            f"Season note: {profile['seasonal_note']}",
            f"Dress modesty: {profile['modesty']}",
            f"Formality baseline: {profile['formality_baseline']}",
            f"Cultural notes: {profile['cultural_notes']}",
            f"Local style vibe: {profile['local_vibe']}",
            f"Fabric tips: {profile['fabric_tips']}",
            f"Avoid: {profile['avoid']}",
            "",
            constraint,
            "[END LOCATION PREFERENCES]" if mode == "travel" else "[END LOCAL CONTEXT]",
        ]
        return "\n".join(lines)

    # ── Hybrid fallback: ask the model to infer norms for this place ──────────
    lines = [
        header,
        f"Location: {label}",
        "No curated profile is available for this place. Using your own knowledge of "
        f"{label}, infer its typical climate and current season, local dress norms and "
        "modesty expectations, formality baseline, and characteristic local style. Apply "
        "them as described below.",
        "",
        constraint,
        "[END LOCATION PREFERENCES]" if mode == "travel" else "[END LOCAL CONTEXT]",
    ]
    return "\n".join(lines)


# ── Live dress guidelines (Phase 2 — Tavily-backed middle tier) ───────────────

def _mode_texts(mode: Mode) -> tuple[str, str]:
    """(header, constraint) for the given mode — mirrors the sync builder."""
    if mode == "travel":
        return (
            "[DESTINATION LOCATION PREFERENCES]",
            "Treat the local dress norms and modesty level as CONSTRAINTS when choosing "
            "wardrobe items: prefer pieces that respect them, suggest cover-ups or layers "
            "from the user's closet where coverage is needed (e.g. temples/mosques/conservative "
            "areas), and never recommend items that would violate local norms. Reflect the most "
            "important point in the trip_summary.location_etiquette field.",
        )
    return (
        "[LOCAL CONTEXT]",
        "Factor the local climate and everyday appropriateness for this place into the "
        "recommendation and its weather/style scoring. Favour items suited to the typical "
        "local conditions and dress sensibilities.",
    )


async def _fetch_live_dress_guidelines(label: str) -> dict[str, Any] | None:
    """Tavily-backed dress guidance for a destination. None when unavailable."""
    query = (
        f"What should visitors wear in {label}? Local dress code, modesty norms, "
        "religious site clothing requirements, and cultural clothing etiquette for tourists."
    )
    return await web_intelligence.cached_search(
        query,
        namespace="dress-guidelines",
        key=label,
        ttl_seconds=DRESS_GUIDELINES_TTL_S,
    )


async def build_location_context_block_async(name: str, *, mode: Mode = "travel") -> str:
    """Location-context block with the live web-guidance middle tier.

    Static-first: curated destinations never trigger a web call. Non-curated
    destinations get Tavily guidance (cached 30 days, shared across users);
    when that's unavailable the existing LLM-infer fallback applies, so the
    output is never worse than ``build_location_context_block``.
    """
    if not name or not name.strip():
        return ""

    label = name.strip()
    if get_location_profile(label):
        return build_location_context_block(label, mode=mode)

    live = await _fetch_live_dress_guidelines(label)
    if not live:
        return build_location_context_block(label, mode=mode)

    header, constraint = _mode_texts(mode)
    sources_line = web_intelligence.format_sources_line(live)
    lines = [
        header,
        f"Location: {label}",
        f"Dress guidance (live web research): {live['answer']}",
    ]
    if sources_line:
        lines.append(sources_line)
    lines += [
        "",
        constraint,
        "[END LOCATION PREFERENCES]" if mode == "travel" else "[END LOCAL CONTEXT]",
    ]
    return "\n".join(lines)
