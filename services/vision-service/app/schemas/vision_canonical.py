"""
Canonical vision preview shapes + normalization of messy LLM JSON.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.closet import _coerce_str_list, coerce_closet_category
from app.schemas.validators import strip_string


def normalize_confidence_value(value: Any) -> float:
    """Coerce AI confidence to 0.0–1.0 (handles 0–100 percentages)."""
    if value is None:
        return 0.0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if f > 1.0:
        if f <= 100.0:
            f = f / 100.0
        else:
            f = 1.0
    if f < 0.0:
        return 0.0
    return f


def _first_str(*vals: Any) -> Optional[str]:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _merge_occasion_fields(d: dict[str, Any]) -> list[str]:
    raw = d.get("occasions")
    if raw is None:
        raw = d.get("occasion")
    if raw is None:
        raw = d.get("occasion_tags")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.replace(";", ",").split(",") if s.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if x and str(x).strip()]
    return []


def _merge_season_fields(d: dict[str, Any]) -> list[str]:
    raw = d.get("season")
    if raw is None:
        raw = d.get("season_tags")
    if raw is None:
        return []
    return _coerce_str_list(raw)


def _merge_style_tags(d: dict[str, Any]) -> list[str]:
    raw = d.get("style_tags")
    if raw is None:
        raw = d.get("tags")
    if raw is None:
        return []
    if isinstance(raw, str):
        t = raw.strip()
        return [t] if t else []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if x and str(x).strip()]
    return []


def normalize_vision_ai_dict(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}

    name = _first_str(raw.get("name"), raw.get("title")) or "Clothing Item"
    category_src = _first_str(
        raw.get("category"),
        raw.get("garment_type"),
        raw.get("garment_category"),
        raw.get("type"),
        raw.get("item_category"),
    )
    subcategory = _first_str(raw.get("subcategory"), raw.get("subtype"))

    color = _first_str(
        raw.get("color"),
        raw.get("color_primary"),
        raw.get("primary_color"),
        raw.get("dominant_color"),
    )
    brand = _first_str(raw.get("brand"))
    material = _first_str(raw.get("material"), raw.get("fabric"))
    pattern = _first_str(raw.get("pattern"))

    description = _first_str(
        raw.get("description"),
        raw.get("notes"),
        raw.get("summary"),
    )

    conf = normalize_confidence_value(
        raw.get("confidence") if raw.get("confidence") is not None else raw.get("confidence_score")
    )

    merged: dict[str, Any] = {
        "name": name,
        "category": category_src or "other",
        "subcategory": subcategory,
        "color": color,
        "brand": brand,
        "material": material,
        "pattern": pattern,
        "season": _merge_season_fields(raw),
        "occasions": _merge_occasion_fields(raw),
        "description": description,
        "confidence": conf,
        "style_tags": _merge_style_tags(raw),
        "eco_score": raw.get("eco_score"),
    }
    if merged["eco_score"] is not None:
        try:
            merged["eco_score"] = float(merged["eco_score"])
        except (TypeError, ValueError):
            merged["eco_score"] = None
    return merged


class NormalizedVisionAIOutput(BaseModel):
    model_config = {"str_strip_whitespace": True}

    name: str = Field(default="Clothing Item", min_length=1, max_length=200)
    category: str = Field(default="other", max_length=100)
    subcategory: Optional[str] = Field(None, max_length=100)
    color: Optional[str] = Field(None, max_length=50)
    brand: Optional[str] = Field(None, max_length=100)
    material: Optional[str] = Field(None, max_length=100)
    pattern: Optional[str] = Field(None, max_length=100)
    season: list[str] = Field(default_factory=list)
    occasions: list[str] = Field(default_factory=list)
    description: Optional[str] = Field(None, max_length=1000)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    style_tags: list[str] = Field(default_factory=list)
    eco_score: Optional[float] = Field(None, ge=0, le=10)

    @field_validator("name", "subcategory", "color", "brand", "material", "pattern", "description", mode="before")
    @classmethod
    def strip_opt(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            s = strip_string(v)
            return s if s else None
        return v

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: Any) -> str:
        c = coerce_closet_category(str(v) if v is not None else None)
        return str(c)

    @field_validator("season", mode="before")
    @classmethod
    def v_season(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    @field_validator("occasions", mode="before")
    @classmethod
    def v_occ(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.replace(";", ",").split(",") if s.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if x and str(x).strip()]
        return []

    @field_validator("style_tags", mode="before")
    @classmethod
    def v_tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            t = v.strip()
            return [t] if t else []
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if x and str(x).strip()]
        return []

    @field_validator("confidence", mode="before")
    @classmethod
    def v_conf(cls, v: Any) -> float:
        return normalize_confidence_value(v)


def parse_vision_ai_payload(raw: Any, *, source: Literal["openai", "bulk", "fallback"] = "openai") -> NormalizedVisionAIOutput:
    if not isinstance(raw, dict):
        raw = {}
    try:
        merged = normalize_vision_ai_dict(raw)
        return NormalizedVisionAIOutput.model_validate(merged)
    except Exception:
        return NormalizedVisionAIOutput(
            name="Clothing Item",
            category="other",
            description=f"Could not parse vision payload ({source}). Please edit before saving.",
            confidence=0.0,
        )


def normalized_to_legacy_upload_dict(n: NormalizedVisionAIOutput) -> dict[str, Any]:
    return {
        "name": n.name,
        "category": n.category,
        "color": n.color,
        "brand": n.brand or "",
        "material": n.material or "",
        "pattern": n.pattern or "",
        "occasion": list(n.occasions),
        "occasions": list(n.occasions),
        "season": list(n.season),
        "tags": list(n.style_tags),
        "eco_score": n.eco_score,
        "confidence": n.confidence,
        "confidence_score": n.confidence,
        "notes": n.description,
        "description": n.description,
        "subcategory": n.subcategory,
    }


def normalized_to_bulk_api_dict(
    n: NormalizedVisionAIOutput,
    *,
    raw: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    season_tags = [t[:1].upper() + t[1:].lower() if t else t for t in n.season] if n.season else []
    out: dict[str, Any] = {
        "name": n.name,
        "category": n.category,
        "subcategory": n.subcategory or "Unknown",
        "description": n.description or "",
        "primary_color": n.color or "Unknown",
        "secondary_colors": [],
        "pattern": n.pattern or "Unknown",
        "material": n.material or "Unknown",
        "occasion_tags": n.occasions if n.occasions else ["Casual"],
        "season_tags": season_tags,
        "style_tags": n.style_tags,
        "fit": "Regular",
        "eco_score": n.eco_score,
        "brand": n.brand or "",
        "confidence_score": n.confidence,
        "warnings": [],
    }
    if raw:
        for k in ("secondary_colors", "fit", "warnings"):
            if raw.get(k) is not None:
                out[k] = raw[k]
    return out
