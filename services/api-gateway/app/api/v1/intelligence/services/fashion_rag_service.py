"""Fashion Knowledge Base RAG service.

Manages a seeded corpus of fashion documents. On first request it lazily
seeds the table (idempotent — skips if already populated). Documents are
embedded with OpenAI and searched with pgvector cosine similarity.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding_service import (
    _DEFAULT_LIMIT,
    generate_text_embedding,
    pgvector_cosine_search,
)
from app.core.logging import get_logger
from app.models.rag import FashionKnowledgeDocument
from app.rag.query_builder import (
    build_fashion_knowledge_query,
    extract_keywords,
    infer_query_signals,
)
from app.rag.rerank import rerank_fashion_documents

logger = get_logger("fashion_rag_service")

# ── Seed corpus ───────────────────────────────────────────────────────────────

_KNOWLEDGE_SEED: list[dict[str, Any]] = [
    {
        "title": "Color Matching Fundamentals",
        "category": "color",
        "season": None,
        "occasion": None,
        "tags": ["color theory", "palette", "contrast"],
        "content": (
            "Color matching is the foundation of great outfits. Complementary colors (opposite "
            "on the color wheel, e.g. blue and orange) create bold contrast. Analogous colors "
            "(adjacent, e.g. navy, teal, and green) create harmonious, sophisticated looks. "
            "Neutral colors (black, white, grey, beige, navy) pair with almost anything. "
            "When in doubt, build a monochromatic outfit in one color family — different shades "
            "of blue always work together. Avoid mixing more than three colors in one outfit. "
            "Warm tones (red, orange, yellow) energize; cool tones (blue, green, purple) calm. "
            "A pop of color works best when the rest of the outfit is neutral."
        ),
    },
    {
        "title": "Business Casual Dressing Guide",
        "category": "occasion",
        "season": None,
        "occasion": "business casual",
        "tags": ["work", "office", "smart casual"],
        "content": (
            "Business casual sits between formal business and casual wear. For men: chinos or "
            "tailored trousers (no jeans), a button-down shirt or polo (no tie required), loafers "
            "or Oxford shoes, and an optional blazer. For women: blouses, fitted trousers, midi "
            "skirts, dresses with a blazer, or tailored jumpsuits. Avoid: ripped clothing, graphic "
            "tees, athletic wear, flip-flops, and overly revealing styles. Colors: navy, grey, "
            "burgundy, camel, and white are safe choices. Add personality through accessories — "
            "a quality watch, belt, or structured bag elevates the look instantly."
        ),
    },
    {
        "title": "Formal Outfit Rules",
        "category": "occasion",
        "season": None,
        "occasion": "formal",
        "tags": ["black tie", "gala", "formal", "evening"],
        "content": (
            "Formal dress codes require precision. Black tie: tuxedo or dark suit with bow tie "
            "for men; floor-length gown or formal midi dress for women. Cocktail attire: "
            "knee-length dress or chic separates for women; dark suit with tie for men. "
            "Key formal rules: ensure garments are well-fitted and wrinkle-free; shoes must be "
            "polished leather (men) or elegant heels/formal flats (women); accessories should be "
            "minimal and high-quality. Avoid: casual fabrics like denim or cotton, bright logos, "
            "sneakers. Dark colors (black, navy, charcoal) are classic; jewel tones (emerald, "
            "sapphire) add personality without breaking formality."
        ),
    },
    {
        "title": "Wedding Guest Outfit Guide",
        "category": "occasion",
        "season": None,
        "occasion": "wedding",
        "tags": ["wedding", "guest", "ceremony"],
        "content": (
            "As a wedding guest, dress to celebrate without outshining the couple. Avoid white, "
            "ivory, and cream (reserved for the bride). Avoid all-black unless it is an evening "
            "wedding. Smart-casual weddings: midi dresses, floral prints, tailored blazer with "
            "trousers. Formal weddings: floor-length or tea-length dress, dark suit or tuxedo. "
            "Beach/garden weddings: light fabrics (chiffon, linen), wedge heels or flats (avoid "
            "stilettos on grass), floral or pastel tones. Indoor evening weddings: deeper, richer "
            "colors work well. Always check the venue for footwear suitability."
        ),
    },
    {
        "title": "Summer Packing & Dressing",
        "category": "seasonal",
        "season": "summer",
        "occasion": "travel",
        "tags": ["summer", "hot weather", "packing", "breathable"],
        "content": (
            "Summer dressing prioritizes breathability and sun protection. Choose natural fabrics: "
            "linen, cotton, chambray, and lightweight rayon. Colors: whites, pastels, and bright "
            "colors reflect heat better than dark tones. Key summer items: light-wash jeans or "
            "chinos, breezy blouses and tanks, dresses and shorts, sandals and lightweight sneakers. "
            "Packing for summer travel: pack light colors to mix and match; include sun hat, "
            "sunglasses, and sunscreen SPF 50+. For a week trip: 5 tops, 3 bottoms, 2 dresses, "
            "2 pairs of shoes, 1 light layer for air-conditioned spaces, swimwear if relevant."
        ),
    },
    {
        "title": "Winter Dressing & Layering",
        "category": "seasonal",
        "season": "winter",
        "occasion": "travel",
        "tags": ["winter", "cold weather", "layering", "thermal"],
        "content": (
            "Winter dressing is about strategic layering. The three-layer system: base layer "
            "(thermal or moisture-wicking), mid layer (fleece, sweater, or cardigan for insulation), "
            "outer layer (waterproof/windproof coat). Key winter fabrics: wool, cashmere, fleece, "
            "and down. Cold-weather essentials: thermal leggings, chunky-knit sweaters, waterproof "
            "boots, wool coat or puffer jacket, beanie, gloves, and scarf. Packing for winter "
            "travel: pack in neutrals (black, grey, camel) so everything coordinates. One pair "
            "of waterproof boots works for most activities. Compress bulky items with packing cubes."
        ),
    },
    {
        "title": "Rainy Weather Outfit Strategies",
        "category": "weather",
        "season": None,
        "occasion": "travel",
        "tags": ["rain", "waterproof", "wet weather"],
        "content": (
            "Dressing for rain requires both practicality and style. Key pieces: waterproof jacket "
            "or trench coat, water-resistant boots (ankle or knee-high), and an umbrella. Avoid: "
            "suede shoes (water-damaged easily), white jeans (can become see-through), and very "
            "wide-leg trousers (absorb puddle splashes). Best fabrics in rain: synthetic blends, "
            "treated cotton, and nylon. Style tip: a belted trench coat looks polished in rain. "
            "For extended rainy destinations, pack rubber boots for heavy downpours and keep "
            "a compact umbrella in your bag at all times."
        ),
    },
    {
        "title": "Travel Capsule Wardrobe Principles",
        "category": "travel",
        "season": None,
        "occasion": "travel",
        "tags": ["capsule", "travel", "versatile", "minimalist"],
        "content": (
            "A travel capsule wardrobe maximizes outfits from minimal items. Core rules: choose "
            "a neutral base (black, white, navy, grey) and add 2–3 accent colors. Every item "
            "should pair with at least 3 others. Prioritize versatile pieces: dark jeans work "
            "for day and evening, a blazer dresses up any outfit, a white shirt is infinitely "
            "remixable. For one week: 4 tops, 2 bottoms, 1 dress/jumpsuit, 2 pairs of shoes "
            "(one casual, one smart), 1 jacket. Fabrics: wrinkle-resistant fabrics (jersey, "
            "synthetic blends) save space. Roll clothes instead of folding to minimize creasing."
        ),
    },
    {
        "title": "Layering Principles for All Seasons",
        "category": "styling",
        "season": None,
        "occasion": None,
        "tags": ["layering", "styling", "versatile"],
        "content": (
            "Layering adds dimension and adaptability to any outfit. Rule of odd numbers: layer "
            "in 3 pieces for visual interest (e.g., tee + shirt + jacket). Proportion matters: "
            "pair slim base layers with voluminous outer layers and vice versa. Tuck in a shirt "
            "to define the waist when layering. Color layering: keep layers in the same tonal "
            "family or use the outer layer as a neutral frame for a colorful inner layer. "
            "Texture layering: mix smooth and textured fabrics (silk under tweed, cotton under "
            "leather) for richness. Light layering (spring/fall): denim jacket + light scarf; "
            "Heavy layering (winter): thermal + chunky knit + structured coat."
        ),
    },
    {
        "title": "Smart Casual Style Guide",
        "category": "occasion",
        "season": None,
        "occasion": "smart casual",
        "tags": ["smart casual", "elevated casual", "dinner"],
        "content": (
            "Smart casual is the most versatile dress code — elevated but not formal. Key formula: "
            "one elevated piece (blazer, tailored trouser, structured dress) paired with one casual "
            "piece (dark jeans, a simple tee). For men: dark slim-fit jeans + button-down or knit "
            "sweater + leather shoes or smart sneakers. For women: tailored trousers + silk blouse, "
            "or a midi dress + denim jacket, or a jumpsuit with heeled mules. Avoid: athletic "
            "wear, overly casual graphics, flip-flops. Footwear is key: Chelsea boots, loafers, "
            "or clean white sneakers elevate a smart casual look instantly."
        ),
    },
    {
        "title": "Shoe Matching Rules",
        "category": "styling",
        "season": None,
        "occasion": None,
        "tags": ["shoes", "footwear", "coordination"],
        "content": (
            "Shoes make or break an outfit. Classic rules: match shoe color to belt color (men). "
            "Nude shoes elongate the leg and pair with almost any outfit. White sneakers are the "
            "most versatile casual shoe — wear with jeans, chinos, dresses, or shorts. Brown shoes "
            "work best with earth tones, navy, and grey — avoid with black trousers for formal "
            "looks. Black shoes pair with most colors except brown. Shoe-to-occasion matching: "
            "Oxford/Derby for formal/business; loafers for smart casual; sneakers for casual; "
            "boots for casual to smart casual; sandals for casual and beach. Heel height: "
            "higher heels dress up an outfit; flat or low block heels keep it grounded."
        ),
    },
    {
        "title": "Accessory Coordination Guide",
        "category": "styling",
        "season": None,
        "occasion": None,
        "tags": ["accessories", "jewelry", "bags", "belts"],
        "content": (
            "Accessories complete and elevate any look. Metal matching rule: mix warm metals "
            "(gold, bronze) or cool metals (silver, gunmetal) — avoid mixing both in one outfit. "
            "Belt rule: match belt to shoes in formal settings; contrast is acceptable casually. "
            "Bag coordination: structured bags dress up; slouchy bags dress down. Jewelry: less "
            "is more for formal occasions; layer and experiment for casual looks. Scarves are "
            "versatile: wear as neck scarf, hair accessory, or bag charm. Sunglasses should "
            "complement face shape: aviators for oval faces, wayfarer for square faces, cat-eye "
            "for round faces. Hats: wide-brim for summer/resort; beanies for winter casual; "
            "fedoras for smart casual or travel."
        ),
    },
    {
        "title": "Capsule Wardrobe Building Rules",
        "category": "wardrobe",
        "season": None,
        "occasion": None,
        "tags": ["capsule wardrobe", "minimalist", "essentials"],
        "content": (
            "A capsule wardrobe is a curated collection where every item works together. "
            "The 10 essential pieces: white shirt, dark jeans, black trousers, little black dress "
            "or equivalent, white tee, cashmere/knit sweater, blazer, trench coat, tailored "
            "chinos, and versatile mid-layer. Color strategy: 70% neutrals, 20% accent colors, "
            "10% pattern/print. Quality over quantity: invest in well-constructed basics and save "
            "on trendy pieces. Care rule: items with more versatility (worn 30+ times per year) "
            "justify higher investment. Review your capsule seasonally: archive items not worn "
            "in 12 months. The goal is 37 items that create 100+ outfit combinations."
        ),
    },
    {
        "title": "Beach and Resort Packing",
        "category": "travel",
        "season": "summer",
        "occasion": "beach",
        "tags": ["beach", "resort", "swimwear", "tropical"],
        "content": (
            "Beach and resort packing prioritizes lightness and versatility. Essentials: swimwear "
            "(2 pieces minimum for alternating), cover-ups (sarong or kaftan), sun hat, sandals, "
            "sunglasses, sunscreen SPF 50+. Clothing: light linen or cotton shirts, shorts, "
            "casual dresses, lightweight trousers for evening. Evening at resort: one smart casual "
            "outfit for dinner (linen shirt + chinos for men; sundress + wedges for women). "
            "Shoes: flip-flops for beach, sandals for exploring, one pair of smart-casual shoes "
            "for evening. Pack a small crossbody or tote bag. Fabrics: quick-dry synthetics for "
            "activewear and swimwear; linen and cotton for all-day wear."
        ),
    },
    {
        "title": "Body Fit and Proportion Guidelines",
        "category": "fit",
        "season": None,
        "occasion": None,
        "tags": ["fit", "proportion", "silhouette", "body"],
        "content": (
            "Good fit is the single biggest factor in how well clothes look. Shoulders: "
            "jacket/shirt shoulders should sit at the shoulder bone edge — too wide looks sloppy, "
            "too narrow restricts movement. Waist: defining the waist creates shape; high-waisted "
            "bottoms lengthen legs. Trouser break: trousers should break once at the top of the "
            "shoe for a modern look. Sleeve length: shirt sleeves show 0.5cm beyond blazer sleeve. "
            "Proportion balancing: wide-leg trousers pair with a fitted or tucked-in top; "
            "oversized top works with slim bottom; cropped top elongates with high-waisted bottoms. "
            "Always prioritize comfort and movement — clothes should never restrict or pull."
        ),
    },
    {
        "title": "Skin Tone Color Matching Guide",
        "category": "color",
        "season": None,
        "occasion": None,
        "tags": ["skin tone", "undertone", "color matching", "warm cool neutral"],
        "content": (
            "Skin tone and undertone are the most personal factor in color selection. "
            "Warm undertones (golden, peachy, yellow-based skin): best colors are earth tones — "
            "camel, terracotta, rust, olive, mustard yellow, warm browns, off-white/cream, warm reds "
            "like tomato red or coral. Avoid: cool icy tones, pastel lavender, cool pinks. "
            "Cool undertones (pink, rosy, blue-based skin): best colors are jewel tones — "
            "sapphire blue, emerald green, true white, burgundy, plum, cool greys, silver accents, "
            "lavender, icy pastels. Avoid: warm oranges, warm yellows, strong earth tones. "
            "Neutral undertones: versatile — almost all colors work; use contrast level to guide. "
            "Deep/rich skin tones carry vivid saturated colors beautifully — jewel tones, rich "
            "mustard, coral, bright white all pop. Avoid low-contrast beige near the face. "
            "Fair/light skin tones look striking with high-contrast combinations (navy + white, "
            "black + white) and soft pastels; avoid very pale tones that wash out. "
            "Olive/medium skin with warm undertone: warm earthy tones and jewel tones both work well. "
            "Always match clothing color to undertone, not just skin darkness level."
        ),
    },
    {
        "title": "Body Type Dressing Guide",
        "category": "fit",
        "season": None,
        "occasion": None,
        "tags": ["body type", "silhouette", "hourglass", "pear", "apple", "rectangle", "petite", "tall"],
        "content": (
            "Dress to flatter your natural body type and proportions. "
            "Hourglass (balanced shoulders and hips, defined waist): wrap dresses, fitted blouses, "
            "high-waisted trousers, belted coats. Avoid: boxy shapes that hide the waist. "
            "Pear / triangle (narrower shoulders, wider hips): emphasise the upper body with "
            "boat necks, statement shoulders, bright tops; choose darker bottoms in straight cuts. "
            "Apple / round (weight around the midsection): empire waist dresses, A-line skirts, "
            "flowy tops, vertical stripe details. Avoid: clingy fabrics around the middle. "
            "Rectangle / straight (similar shoulder and hip width, minimal waist): create curves "
            "with peplum tops, ruffles, cropped jackets, wide-leg trousers. Belt everything. "
            "Inverted triangle (broader shoulders, narrower hips): balance with voluminous bottoms, "
            "wide-leg trousers, A-line skirts, avoid heavy shoulder details. "
            "Petite frames (under 5'4\"): high-waisted bottoms elongate legs; cropped tops; "
            "avoid oversized or heavily layered looks that overwhelm the silhouette. "
            "Tall frames (over 5'9\"): wide-leg trousers, longline coats, maxi dresses all work "
            "beautifully; horizontal stripes add volume; cropped lengths are flattering. "
            "Plus-size: vertical lines, wrap silhouettes, well-fitted clothes (never too baggy or "
            "too tight). Structured pieces provide shape and confidence."
        ),
    },
    {
        "title": "Pattern Mixing Rules",
        "category": "styling",
        "season": None,
        "occasion": None,
        "tags": ["patterns", "prints", "mixing", "stripes", "florals", "checks"],
        "content": (
            "Mixing patterns adds personality but requires rules to avoid clashing. "
            "Rule 1 — Scale contrast: always pair a large-scale pattern with a small-scale pattern "
            "(e.g. large floral + thin stripe). Never mix two equally-sized patterns. "
            "Rule 2 — Colour connection: at least one colour must appear in both patterns; this "
            "creates visual harmony (e.g. a blue stripe top + a blue/white floral skirt). "
            "Rule 3 — Pattern hierarchy: let one pattern dominate (wear it on the larger body area) "
            "and keep the second pattern as an accent. "
            "Safe combinations: stripes + florals; stripes + checks (different scales); "
            "animal print + geometric (animal print acts as a neutral). "
            "Difficult combinations: two large florals; two plaids; two different animal prints. "
            "Solids as anchors: a solid-colored third piece (blazer, shoes, bag) ties mixed "
            "patterns together instantly. "
            "When in doubt: mix one pattern with one texture (e.g. floral blouse + textured tweed "
            "skirt) — texture acts like a second pattern without the risk of clashing."
        ),
    },
    {
        "title": "Color Season Analysis (Spring Summer Autumn Winter)",
        "category": "color",
        "season": None,
        "occasion": None,
        "tags": ["color season", "seasonal palette", "spring summer autumn winter", "personal color analysis"],
        "content": (
            "Color season analysis matches personal coloring to a seasonal palette. "
            "SPRING (warm, light, clear): warm skin with peachy/golden undertone, light or hazel eyes, "
            "golden/strawberry blonde or light auburn hair. Best colors: coral, peach, warm yellow, "
            "light warm greens, turquoise, ivory, camel. Avoid: icy pastels, cool greys, black near face. "
            "SUMMER (cool, light, muted): cool skin with pinkish undertone, blue/grey/cool eyes, "
            "ash blonde or light cool brown hair. Best colors: dusty rose, lavender, powder blue, soft "
            "grey, taupe, muted navy, soft white. Avoid: warm oranges, earth tones, pure black. "
            "AUTUMN (warm, deep, muted): golden/olive/warm skin, amber/hazel/brown/green eyes, "
            "chestnut/auburn/warm brown hair. Best colors: rust, burnt orange, olive, dark camel, forest "
            "green, warm brown, teal, gold. Avoid: cool icy pastels, pure black, cool reds. "
            "WINTER (cool, deep, clear): cool or neutral skin, dark/intense eyes, dark brown/black "
            "or starkly contrasted hair. Best colors: true white, jet black, navy, royal blue, "
            "emerald, ruby red, fuchsia, icy pastels for contrast. Avoid: earth tones, warm yellows."
        ),
    },
    {
        "title": "Denim Styling and Versatility Guide",
        "category": "styling",
        "season": None,
        "occasion": None,
        "tags": ["denim", "jeans", "denim jacket", "smart casual", "casual"],
        "content": (
            "Denim is the most versatile fabric in any wardrobe. Wash guide: dark wash denim is most "
            "formal and can dress up for smart-casual evenings; medium wash is truly everyday versatile; "
            "light wash is casual and summery; distressed/ripped is very casual only. "
            "Slim-fit jeans: the most universal cut — dress up with loafers and a blazer for smart "
            "casual; dress down with sneakers and a hoodie for weekend. Wide-leg jeans: fashion-forward; "
            "balance with a fitted or cropped top tucked in at the waist. Straight-leg: combines "
            "classic with modern; works with everything. Skinny jeans: best elongated with pointed "
            "toe footwear; pair with chunky knit or oversized blazer for balance. "
            "Canadian Tuxedo rule: head-to-toe denim works only when the washes are clearly different "
            "(e.g. dark jacket + light jeans). Avoid matching washes — it reads as matchy. "
            "Denim jacket: the perfect third piece for casual to smart-casual; wear over a dress for "
            "unexpected contrast; over a white tee and chinos for a classic look."
        ),
    },
    {
        "title": "Business Formal and Power Dressing Guide",
        "category": "occasion",
        "season": None,
        "occasion": "business formal",
        "tags": ["business formal", "power dressing", "corporate", "interview", "boardroom"],
        "content": (
            "Business formal requires precision and authority. Men: tailored suit (navy, charcoal, "
            "or grey), white or pale blue dress shirt, conservative tie, Oxford or Derby shoes, "
            "matching belt. Women: tailored trouser suit, pencil skirt + blazer, structured shift "
            "dress, or a formal pantsuit. Colors: navy, charcoal, black, and grey project authority. "
            "Power dressing principles: ensure perfect fit — tailoring is non-negotiable; choose "
            "structured fabrics (wool, wool-blend, crepe); avoid overly trendy silhouettes; quality "
            "accessories elevate (leather portfolio, structured bag, quality watch). "
            "Interview dressing: mirror the company dress code one level up — business casual company "
            "means wear business formal for the interview. Grooming is as important as the outfit. "
            "Women's power colors: navy (trust), red (authority/confidence), black (sharp/serious), "
            "grey (neutral/analytical). Men's suit color guide: navy = approachable authority; "
            "charcoal = serious/formal; mid-grey = versatile everyday; black = most formal only."
        ),
    },
    {
        "title": "Monochrome and Tonal Dressing Guide",
        "category": "styling",
        "season": None,
        "occasion": None,
        "tags": ["monochrome", "tonal", "one color", "color blocking", "head to toe"],
        "content": (
            "Monochrome (head-to-toe one color) is sophisticated and elongating. Key rules: "
            "vary the texture and fabric weight to avoid flatness — pair a satin blouse with "
            "structured trousers in the same color; matte + shiny works well. "
            "Tonal dressing (different shades of the same color family): even easier to execute; "
            "combine cream + beige + camel for an elevated neutral look; or navy + cobalt + sky blue. "
            "All-white: clean and powerful in summer; ensure pieces are the same shade of white "
            "or deliberately contrast warm white vs pure white for intentional effect. "
            "All-black: the most universally flattering monochrome; vary textures (velvet, leather, "
            "knit, jersey) to create depth. "
            "Color blocking (two or more distinct bold colors): keep to 2-3 colors maximum; use "
            "complementary colors (opposite on the color wheel) for drama; use analogous colors "
            "for a more wearable look. Neutral breaks between blocks (a white belt, nude shoes) "
            "prevent the look from becoming overwhelming."
        ),
    },
]


# ── Service functions ─────────────────────────────────────────────────────────


async def ensure_seeded(session: AsyncSession) -> None:
    """Seed missing fashion knowledge documents. Idempotent — only inserts missing titles."""
    existing_titles_result = await session.execute(select(FashionKnowledgeDocument.title))
    existing_titles = {row[0] for row in existing_titles_result.all()}

    missing = [doc for doc in _KNOWLEDGE_SEED if doc["title"] not in existing_titles]
    if not missing:
        return

    logger.info("fashion_kb_seeding", new_docs=len(missing), total_seed=len(_KNOWLEDGE_SEED))
    for doc in missing:
        content_for_embedding = f"Title: {doc['title']}. {doc['content']}"
        embedding = await generate_text_embedding(content_for_embedding)
        db_doc = FashionKnowledgeDocument(
            title=doc["title"],
            content=doc["content"],
            category=doc["category"],
            season=doc.get("season"),
            occasion=doc.get("occasion"),
            tags={"tags": doc.get("tags", [])},
            embedding=embedding,
        )
        session.add(db_doc)
    logger.info("fashion_kb_seeded", added=len(missing))


async def search_fashion_knowledge(
    session: AsyncSession,
    query: str,
    limit: int = _DEFAULT_LIMIT,
    category: str | None = None,
    occasion: str | None = None,
    weather: str = "",
) -> list[dict[str, Any]]:
    """Retrieve relevant fashion knowledge documents for a query."""
    await ensure_seeded(session)

    inferred = infer_query_signals(query)
    effective_occasion = occasion or inferred.get("occasion")
    effective_season = inferred.get("season")
    effective_weather = weather or inferred.get("weather") or ""

    enriched_query = build_fashion_knowledge_query(
        query,
        occasion=effective_occasion,
        weather=effective_weather,
        category=category,
    )

    docs: list[dict[str, Any]] = []
    embedding = await generate_text_embedding(enriched_query)
    if embedding:
        fetch_limit = min(max(limit * 3, limit), 15)
        rows = await pgvector_cosine_search(
            session,
            table="fashion_knowledge_documents",
            embedding=embedding,
            user_id=None,
            limit=fetch_limit,
            threshold=0.55,
            filter_category=category,
        )
        docs = [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "content": r["content"],
                "category": r["category"],
                "season": r.get("season"),
                "occasion": r.get("occasion"),
                "relevance_score": round(float(r.get("similarity_score", 0)), 3),
            }
            for r in rows
        ]

    if not docs:
        docs = await _keyword_fallback(session, enriched_query, category, limit)

    reranked = rerank_fashion_documents(
        docs,
        occasion=effective_occasion,
        season=effective_season,
        weather=effective_weather or None,
    )
    return reranked[:limit]


async def _keyword_fallback(
    session: AsyncSession,
    query: str,
    category: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Keyword search when embeddings are unavailable or vector search is empty."""
    keywords = extract_keywords(query)
    if not keywords:
        return []

    conditions = []
    for kw in keywords:
        pattern = f"%{kw}%"
        conditions.extend(
            [
                FashionKnowledgeDocument.title.ilike(pattern),
                FashionKnowledgeDocument.content.ilike(pattern),
                FashionKnowledgeDocument.occasion.ilike(pattern),
                FashionKnowledgeDocument.season.ilike(pattern),
            ]
        )

    stmt = select(FashionKnowledgeDocument).where(or_(*conditions))
    if category:
        stmt = stmt.where(FashionKnowledgeDocument.category == category)
    stmt = stmt.limit(limit)

    try:
        result = await session.execute(stmt)
        rows = result.scalars().all()
    except Exception as exc:
        logger.warning("fashion_kb_keyword_fallback_failed", error=str(exc))
        return []

    return [
        {
            "id": str(doc.id),
            "title": doc.title,
            "content": doc.content,
            "category": doc.category,
            "season": doc.season,
            "occasion": doc.occasion,
            "relevance_score": 0.50,
        }
        for doc in rows
    ]


async def get_fashion_context_for_prompt(
    session: AsyncSession,
    query: str,
    limit: int = 5,
    occasion: str | None = None,
    weather: str = "",
) -> str:
    """Return a formatted string of relevant fashion knowledge for LLM prompt injection."""
    docs = await search_fashion_knowledge(session, query, limit=limit, occasion=occasion, weather=weather)
    if not docs:
        return ""
    lines = ["[Fashion Knowledge Context]"]
    for i, doc in enumerate(docs, 1):
        # Use up to 600 chars per document for richer grounding context
        excerpt = doc["content"] if len(doc["content"]) <= 600 else doc["content"][:600] + "…"
        lines.append(f"[SOURCE-{i}] {doc['title']} (relevance: {doc['relevance_score']:.2f})\n{excerpt}")
    return "\n\n".join(lines)
