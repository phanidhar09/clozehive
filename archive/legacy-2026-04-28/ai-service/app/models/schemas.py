from pydantic import BaseModel, Field
from typing import Optional, List, Any


# ── Closet Item ────────────────────────────────────────────
class ClosetItem(BaseModel):
    id: str
    user_id: int = 1
    name: str
    category: Optional[str] = None
    color: Optional[str] = None
    fabric: Optional[str] = None
    pattern: Optional[str] = None
    season: Optional[str] = None
    occasion: Optional[List[str]] = []
    eco_score: Optional[int] = None
    tags: Optional[List[str]] = []
    image_url: Optional[str] = None
    notes: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    price: Optional[float] = None
    wear_count: Optional[int] = 0
    last_worn: Optional[str] = None


# ── Vision ─────────────────────────────────────────────────
class VisionAnalysisResponse(BaseModel):
    garment_type: str = ""
    fabric: str = ""
    color_primary: str = ""
    color_secondary: str = ""
    pattern: str = ""
    season: str = ""
    occasion: List[str] = []
    care_instructions: List[str] = []
    wearing_tips: List[str] = []
    eco_score: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    raw_description: str = ""


# ── Outfit ─────────────────────────────────────────────────
class OutfitRequest(BaseModel):
    closet_items: List[ClosetItem]
    occasion: str = "casual"
    weather: str = "sunny"
    temperature: float = 22.0


class OutfitSuggestion(BaseModel):
    name: str
    item_ids: List[str]
    items: List[dict] = []
    explanation: str
    style_score: float = Field(default=8.0, ge=1.0, le=10.0)
    occasion_fit: str = ""
    weather_fit: str = ""


class OutfitResponse(BaseModel):
    outfits: List[OutfitSuggestion]
    occasion: str
    weather: str
    temperature: float


# ── Packing ────────────────────────────────────────────────
class PackingRequest(BaseModel):
    destination: str
    start_date: str
    end_date: str
    purpose: str = "leisure"
    closet_items: List[ClosetItem]


class WeatherDay(BaseModel):
    date: str
    condition: str
    temp_high: float
    temp_low: float
    description: str


class PackingItem(BaseModel):
    name: str
    category: str
    quantity: int = 1
    reason: str = ""
    available_in_closet: bool = False
    closet_item_id: Optional[str] = None


class DailyOutfitPlan(BaseModel):
    date: str
    weather: WeatherDay
    outfit_suggestion: str
    items_needed: List[str]


class PackingResponse(BaseModel):
    destination: str
    start_date: str
    end_date: str
    duration_days: int
    trip_type: str
    weather_summary: dict
    packing_list: List[PackingItem]
    missing_items: List[PackingItem]
    daily_plan: List[DailyOutfitPlan]
    alerts: List[str]
    packing_item_ids: List[str] = []


# ── Chat ───────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    closet_items: Optional[List[Any]] = []


class ChatResponse(BaseModel):
    reply: str
    suggestions: List[str] = []
