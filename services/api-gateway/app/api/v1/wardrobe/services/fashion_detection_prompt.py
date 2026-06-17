"""
Shared fashion-detection prompt + structured-output schema.

Single source of truth for the multi-item detection contract used by BOTH the
Gemini path (``gemini_service``) and the OpenAI fallback path
(``fashion_analysis_service``). Keeping the prompt here prevents the two callers
from silently drifting apart — historically they held byte-identical copies that
had to be edited in lockstep.

``FashionDetection`` doubles as:
  • a Gemini ``response_schema`` (guaranteed JSON structure), and
  • a Pydantic validator for any provider's raw JSON output.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Detection prompt (shared) ─────────────────────────────────────────────────

FASHION_DETECTION_PROMPT = """\
You are an expert fashion AI with deep knowledge of garment construction, fabric, \
color theory, and wardrobe cataloguing.

TASK: Detect EVERY distinct wearable item visible in this image. Each item becomes \
an independent closet entry — analyse each with the same care as if it were the \
only item in the photo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO DETECT (include ALL of these):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• tops: t-shirt, shirt, blouse, tank top, hoodie, sweatshirt, sweater, cardigan, crop top
• bottoms: jeans, trousers, chinos, shorts, skirt, leggings, joggers, cargo pants
• outerwear: jacket, coat, blazer, parka, windbreaker, trench coat, bomber jacket
• footwear: sneakers, boots, shoes, oxfords, loafers, sandals, heels, slides
• accessories: bag, handbag, backpack, tote, hat, cap, belt, scarf, watch, sunglasses, jewelry
• full-body: dress, jumpsuit, romper, suit, co-ord set

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MULTI-ITEM RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ONE garment = ONE array entry. NEVER merge.
   ✓ Shirt + jeans + sneakers → 3 entries
   ✓ Flat-lay with 5 items → 5 entries
2. FLAT-LAY: every garment gets its own tight bbox — do NOT use one bbox for the whole layout.
3. LAYERED OUTFITS: jacket over shirt → 2 entries, each with its own tight bbox.
4. PARTIAL items >10% visible → include, set segmentation_quality "low".
5. SMALL accessories: belt, watch, sunglasses each get their own entry.
6. Scan ENTIRE image — top-to-bottom, left-to-right — before writing any item.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BBOX RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Fractional coords, (0,0)=top-left, (1,1)=bottom-right.
• Tight around the visible region of THAT item only.
• Never use {x_min:0, y_min:0, x_max:1, y_max:1} unless item truly fills the frame.
• Minimum bbox area: (x_max-x_min)×(y_max-y_min) ≥ 0.005.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COLOR — BE SPECIFIC:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use precise color names. Prefer:
  navy blue, cobalt blue, sky blue, powder blue, teal, turquoise
  forest green, olive green, sage green, mint green, emerald
  crimson, burgundy, coral, salmon, blush pink, hot pink, magenta
  charcoal, slate grey, silver, light grey, off-white, ivory, cream
  camel, tan, khaki, beige, sand, rust, burnt orange, mustard
  black, white — only if truly pure.
Avoid vague terms like "blue", "green", "gray". Pick the most accurate specific shade.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MATERIAL — READ THE FABRIC, NOT THE COLOR:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Look at visible texture and drape:
  • Matte flat weave, slight texture → cotton or linen
  • Diagonal twill pattern, rigid body → denim
  • Shiny, fluid, drapes in liquid folds → silk or satin
  • Fuzzy surface, warm visual weight → wool or fleece
  • Fine ribbing or tight knit → knit / knitwear
  • Smooth high-sheen, plastic-looking → polyester or synthetic
  • Grained or smooth stiff surface with sheen → leather or faux-leather
  • Porous open weave → linen or woven cotton
If texture is not determinable from the image, output "unknown" — never guess.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CATEGORY EDGE CASES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• hoodie, sweatshirt, cardigan → top (not outerwear)
• blazer worn as outermost layer → outerwear
• vest worn as outermost layer → outerwear; vest worn under jacket → do not detect separately
• bodysuit worn as top → top
• leggings → bottom; tights worn with dress → do not detect separately

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OTHER METADATA RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• detection_confidence: 0.0–1.0 (visibility × identification certainty). Min 0.35 to include.
• segmentation_quality: "high" (clean edges), "medium" (some occlusion), "low" (heavily occluded).
• brand: null unless a logo or text label is CLEARLY and FULLY legible. Never guess a brand.
• Use null (not "") for all unknown/unverifiable fields.
• name: format as "<Color> <Subcategory>" e.g. "Navy Slim-Fit Jeans", "Ivory Cable-Knit Sweater".
• description: one concrete sentence — mention the actual item's visible qualities, not generics.

Return ONLY valid JSON — no markdown, no prose, no trailing commas:

{
  "total_items_detected": <integer>,
  "items": [
    {
      "item_id": "item_001",
      "category": "top | bottom | footwear | outerwear | accessory | dress | other",
      "subcategory": "<specific e.g. slim jeans | oversized hoodie | white leather sneakers>",
      "name": "<Color Subcategory e.g. Charcoal Slim-Fit Chinos>",
      "description": "<one specific sentence about this item's visible qualities>",
      "gender": "male | female | unisex",
      "fit": "slim | regular | oversized | relaxed | tailored | null",
      "sleeve_type": "long | short | sleeveless | null",
      "primary_color": "<specific shade e.g. navy blue | charcoal | ivory>",
      "secondary_color": "<specific shade or null>",
      "pattern": "solid | striped | plaid | checked | graphic | floral | animal_print | tie_dye | camo | houndstooth | paisley | null",
      "material": "cotton | denim | leather | faux-leather | polyester | silk | wool | linen | fleece | knit | synthetic | unknown",
      "brand": "<brand name or null>",
      "occasions": ["casual","formal","business","party","travel","gym","beach","date"],
      "season": ["summer","winter","all-season","fall","spring"],
      "style_tags": ["minimal","streetwear","sporty","elegant","vintage","classic","preppy","bohemian","athleisure","workwear"],
      "bbox": {"x_min": 0.05, "y_min": 0.10, "x_max": 0.95, "y_max": 0.90},
      "detection_confidence": 0.95,
      "segmentation_quality": "high | medium | low"
    }
  ]
}

BEFORE SUBMITTING: re-read your output and verify each item has the tightest possible \
bbox, the most specific color name, and a material that matches the visible texture."""


# ── Structured-output schema ──────────────────────────────────────────────────


class DetectionBBox(BaseModel):
    """Fractional (0–1) bounding box, top-left origin."""

    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 1.0
    y_max: float = 1.0


class DetectedItem(BaseModel):
    """One detected wearable item. Mirrors the prompt's per-item JSON contract."""

    item_id: str | None = None
    category: str = "other"
    subcategory: str | None = None
    name: str | None = None
    description: str | None = None
    gender: str | None = None
    fit: str | None = None
    sleeve_type: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    pattern: str | None = None
    material: str | None = None
    brand: str | None = None
    occasions: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)
    bbox: DetectionBBox = Field(default_factory=DetectionBBox)
    detection_confidence: float = 0.8
    segmentation_quality: str = "medium"


class FashionDetection(BaseModel):
    """Top-level detection result. Usable as a Gemini ``response_schema``."""

    total_items_detected: int = 0
    items: list[DetectedItem] = Field(default_factory=list)


def to_detection_dict(parsed: FashionDetection) -> dict[str, Any]:
    """Convert a validated ``FashionDetection`` to the plain dict shape callers expect."""
    items: list[dict[str, Any]] = []
    for idx, item in enumerate(parsed.items):
        d = item.model_dump()
        if not d.get("item_id"):
            d["item_id"] = f"item_{idx + 1:03d}"
        items.append(d)
    return {"total_items_detected": len(items), "items": items}
