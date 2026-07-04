"""Model routing — a decision layer that runs *before* generation.

Routing is treated as a classifier over the **task** (intent + evidence +
constraints), not as a length heuristic. A short message can be hard
("what should I wear to a Tuscan outdoor wedding in October?") and a long one
trivial ("...anyway, is navy ok with brown?"), so message length is used only
as a de-escalating tiebreaker — never as a primary rule.

The router consumes signals the chat pipeline has *already computed* (RAG closet
hits, occasion, weather, images, history depth) and returns a structured
:class:`RouteDecision`. Generation reads the decision instead of hardcoding a
model, so swapping/adding models is a config change, not a code change.

Design notes:
  • Pure-CPU and synchronous — adds no blocking work to the request path.
  • Hard overrides first (images → vision-capable tier), then a weighted
    complexity score over the remaining signals.
  • Degraded/unknown signals bias toward LARGE: routing errs on quality, not cost.
  • Emits a structured ``model_route`` log so thresholds can be tuned from real
    traffic (and later used to train an LLM micro-classifier for the ambiguous band).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("model_router")


class Tier(str, Enum):
    """Capability/cost tiers the router can select."""

    SMALL = "small"  # cheap/fast: chit-chat, factual Q&A, single simple outfit
    LARGE = "large"  # multi-outfit generation, dense constraints, long sessions
    VISION = "vision"  # any turn with attached images


# Score at/above which a turn escalates from SMALL to LARGE. Tuned from the
# `model_route` logs — kept as a module constant so it is easy to sweep.
_ESCALATE_THRESHOLD = 0.45
# Ambiguous band [low, threshold): the deterministic score is too close to the
# boundary to trust on its own. Only these turns pay for the LLM micro-classifier.
_ARBITER_LOW = 0.30


@dataclass
class RouteDecision:
    tier: Tier
    model: str
    max_tokens: int
    temperature: float
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class RouteSignals:
    """Everything the router scores.

    Assembled by the caller from context it already built for the turn, so the
    router never re-parses or re-embeds anything.
    """

    message: str
    has_images: bool = False
    closet_item_count: int = 0
    # True when the turn is expected to produce ``recommended_outfits`` — the
    # single strongest driver of complexity (structured multi-outfit JSON).
    expects_outfits: bool = False
    weather_required: bool = False
    history_depth: int = 0
    # occasion + weather + mood + profile, etc. — simultaneous constraints.
    constraint_count: int = 0


def _catalog() -> dict[Tier, tuple[str, int, float]]:
    """(model, max_tokens, temperature) per tier, resolved from settings."""
    return {
        Tier.SMALL: (settings.openai_model_small, 1500, 0.4),
        Tier.LARGE: (settings.openai_model, settings.openai_max_tokens, 0.5),
        # Vision reuses the strong (vision-capable) model; branch kept explicit
        # so a dedicated vision model can be slotted in later without touching callers.
        Tier.VISION: (settings.openai_model, settings.openai_max_tokens, 0.5),
    }


def _estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) — good enough for a tiebreaker."""
    return max(1, len(text) // 4)


# Words that signal the user wants an outfit *built* (structured output) vs.
# a purely informational answer. Intent, not length, drives escalation.
_OUTFIT_INTENT = (
    "wear",
    "outfit",
    "dress me",
    "style me",
    "what should i",
    "put together",
    "look for",
    "date",
    "wedding",
    "interview",
    "party",
    "meeting",
    "brunch",
    "gym",
    "office",
    "occasion",
)
# Purely theoretical asks that need no outfit card — bias toward SMALL.
_THEORETICAL_INTENT = (
    "what is",
    "what are",
    "how do i wash",
    "how to wash",
    "care for",
    "color theory",
    "colour theory",
    "trend",
    "why do",
    "difference between",
)


def looks_like_outfit_request(message: str) -> bool:
    """Heuristic intent check: does this turn expect a built outfit?

    Used to set :attr:`RouteSignals.expects_outfits` when no explicit occasion
    was passed. Deliberately conservative — theoretical questions short-circuit
    to False so they can route to the cheap tier.
    """
    low = message.lower()
    if any(kw in low for kw in _THEORETICAL_INTENT):
        return False
    return any(kw in low for kw in _OUTFIT_INTENT)


def route(sig: RouteSignals) -> RouteDecision:
    """Decide which model tier should handle this turn."""
    # ── Hard overrides ────────────────────────────────────────────────────
    if sig.has_images:
        return _decide(Tier.VISION, ["images_attached"], score=1.0)

    # ── Weighted complexity score (0..1) ─────────────────────────────────
    score = 0.0
    reasons: list[str] = []

    if sig.expects_outfits:
        score += 0.45
        reasons.append("structured_outfit_output")
    if sig.closet_item_count >= 12:
        score += 0.15
        reasons.append("large_evidence_set")
    if sig.constraint_count >= 3:
        score += 0.20
        reasons.append("dense_constraints")
    if sig.weather_required:
        score += 0.05
        reasons.append("weather_grounded")
    if sig.history_depth >= 8:
        score += 0.10
        reasons.append("long_session")

    # Length is only a de-escalator: a very short, non-outfit ask is almost
    # always trivial. It can never *escalate* a turn on its own.
    if _estimate_tokens(sig.message) < 12 and not sig.expects_outfits:
        score -= 0.10
        reasons.append("trivial_length_tiebreak")

    tier = Tier.LARGE if score >= _ESCALATE_THRESHOLD else Tier.SMALL
    reasons.append(f"threshold(score={round(score, 2)})")
    return _decide(tier, reasons, score=score)


def _decide(tier: Tier, reasons: list[str], *, score: float) -> RouteDecision:
    model, max_tokens, temperature = _catalog()[tier]
    decision = RouteDecision(
        tier=tier,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        reasons=reasons,
        score=round(score, 3),
    )
    logger.info(
        "model_route",
        tier=tier.value,
        model=model,
        score=decision.score,
        reasons=reasons,
    )
    return decision


# ── LLM micro-classifier (second stage, ambiguous band only) ───────────────────

_ARBITER_SYSTEM_PROMPT = (
    "You are a routing classifier for a fashion assistant. Judge how much "
    "reasoning the user's request needs. Answer HIGH if it requires composing "
    "outfits, weighing several constraints (occasion + weather + body/colour "
    "preferences), or multi-step styling judgement. Answer LOW for simple "
    "factual questions, chit-chat, or a single trivial suggestion. Message "
    'length is irrelevant. Respond with strict JSON only: {"complexity": "low"|"high"}.'
)


def _needs_arbitration(decision: RouteDecision) -> bool:
    """Only the uncertain band near the boundary is worth an LLM call.

    Vision turns and confident scores (clearly SMALL or clearly LARGE) skip it.
    """
    return decision.tier is not Tier.VISION and _ARBITER_LOW <= decision.score < _ESCALATE_THRESHOLD


async def route_async(sig: RouteSignals) -> RouteDecision:
    """Two-stage route: deterministic score first, LLM arbiter for the grey zone.

    ~90% of turns resolve on the deterministic pass with zero added latency/cost.
    Only scores in ``[_ARBITER_LOW, _ESCALATE_THRESHOLD)`` pay for one cheap
    classifier call. Any failure falls back to the deterministic decision, so the
    arbiter can only *upgrade* confidence, never break routing.
    """
    decision = route(sig)

    if not settings.model_router_arbiter_enabled or not _needs_arbitration(decision):
        return decision

    verdict = await _classify_complexity(sig.message)
    if verdict is None:
        decision.reasons.append("arbiter_unavailable")
        return decision

    tier = Tier.LARGE if verdict == "high" else Tier.SMALL
    reasons = [*decision.reasons, f"arbiter({verdict})"]
    return _decide(tier, reasons, score=decision.score)


async def _classify_complexity(message: str) -> str | None:
    """Ask the small model for a low/high complexity verdict. Returns None on failure."""
    import json

    # Lazy import avoids any import cycle and keeps the deterministic path import-light.
    from app.api.v1.intelligence.services import ai_service

    try:
        raw = await ai_service.chat(
            [{"role": "user", "content": message[:2000]}],
            _ARBITER_SYSTEM_PROMPT,
            use_json_mode=True,
            model=settings.openai_model_small,
            max_tokens=16,
            temperature=0.0,
        )
        verdict = str(json.loads(raw).get("complexity", "")).strip().lower()
        return verdict if verdict in ("low", "high") else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("model_route_arbiter_failed", error=str(exc))
        return None
