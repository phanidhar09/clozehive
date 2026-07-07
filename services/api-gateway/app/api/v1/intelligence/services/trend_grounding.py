"""Trend grounding for FANI chat — live web context for trend questions (Phase 7).

When a chat message asks about *current* fashion ("what's trending this
summer?", "are skinny jeans still in style?"), the LLM's training data is
stale by definition. This module detects trend intent and fetches a live,
cached Tavily answer to ground the reply in what's actually current.

Cost control: only trend-intent messages trigger a lookup (a small fraction of
chat traffic), answers are cached 24h, and the cache key includes the season
so a January answer never serves a July question. Like every web-intelligence
layer, this is enhancement only — None degrades to the existing
training-data-based reply.

The block's guardrail keeps the closet-grounding contract intact: trends are
styling *inspiration*; recommendations still come ONLY from owned items.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

from app.core import web_intelligence

TREND_TTL_S = 24 * 3600
# Cache key uses a normalized slice of the message: identical questions share
# one fetch; the season prefix stops stale-season answers crossing over.
_KEY_MAX_CHARS = 80

_TREND_PATTERNS = re.compile(
    r"\b("
    r"trend(?:s|ing|y)?|in (?:style|fashion|vogue)|out of (?:style|fashion)|"
    r"still (?:in|cool|fashionable)|this (?:season|summer|winter|spring|fall|autumn|year)|"
    r"right now|currently popular|what'?s (?:hot|new|popular|in)|"
    r"latest (?:fashion|styles?|looks?)|fashion week|street style"
    r")\b",
    re.IGNORECASE,
)


def is_trend_query(message: str) -> bool:
    """True when the message asks about current/seasonal fashion trends."""
    return bool(message and _TREND_PATTERNS.search(message))


def _season(today: date) -> str:
    # Meteorological seasons, northern-hemisphere naming — coarse is fine here:
    # the season tag only partitions the cache and flavours the search query.
    m = today.month
    if m in (12, 1, 2):
        return "winter"
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    return "fall"


def _normalize_key(message: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]+", "", message.lower())
    return re.sub(r"\s+", " ", cleaned).strip()[:_KEY_MAX_CHARS]


async def get_trend_context(message: str, today: date | None = None) -> dict[str, Any] | None:
    """Live trend answer for a trend-intent message. None when not applicable."""
    if not is_trend_query(message):
        return None
    today = today or date.today()
    season = _season(today)
    query = (
        f"Current fashion trends as of {season} {today.year} relevant to this question: "
        f"{message.strip()[:200]} — key colours, silhouettes, styles, and what is "
        "considered dated."
    )
    return await web_intelligence.cached_search(
        query,
        namespace="trends",
        key=f"{season}-{today.year}:{_normalize_key(message)}",
        ttl_seconds=TREND_TTL_S,
    )


# ── Constrained extraction ────────────────────────────────────────────────────
#
# The Tavily answer is sanitized at the web_intelligence chokepoint, but a
# regex denylist is a speed bump, not a boundary. On the chat path we go
# further: the prompt block is built ONLY from allowlisted fashion vocabulary
# extracted from the answer — attacker prose cannot survive, because free web
# text never enters the system prompt at all. Vocabulary misses degrade to
# "no trend context" (the pre-Phase-7 behaviour), never to raw text.
#
# The allowlists are curated, not exhaustive; extend them when real trend
# answers surface vocabulary that gets dropped (log: trend_extraction_empty).
# Terms are matched case-insensitively with hyphens normalized to spaces.

_TREND_COLOURS = (
    "butter yellow", "powder pink", "baby blue", "powder blue", "sky blue", "royal blue",
    "cherry red", "tomato red", "burnt orange", "chocolate brown", "forest green",
    "neon green", "hot pink", "burgundy", "oxblood", "bordeaux", "maroon", "wine",
    "mocha", "espresso", "camel", "tan", "beige", "cream", "ivory", "white", "black",
    "navy", "cobalt", "indigo", "denim blue", "sage", "olive", "emerald", "mint",
    "pistachio", "chartreuse", "lime", "lavender", "lilac", "purple", "plum", "red",
    "crimson", "scarlet", "pink", "fuchsia", "magenta", "blush", "orange", "rust",
    "terracotta", "coral", "peach", "apricot", "yellow", "mustard", "gold", "silver",
    "metallic", "charcoal", "grey", "gray", "taupe", "khaki", "teal", "turquoise", "aqua",
)
_TREND_SILHOUETTES = (
    "wide leg", "barrel leg", "straight leg", "skinny", "slim", "bootcut", "flared",
    "flare", "palazzo", "baggy", "oversized", "boxy", "relaxed", "tailored", "fitted",
    "cropped", "high waisted", "high rise", "low rise", "mid rise", "a line", "column",
    "slip dress", "wrap dress", "shift dress", "shirt dress", "peplum", "balloon",
    "puff sleeve", "drop shoulder", "off the shoulder", "asymmetric", "maxi", "midi",
    "mini", "longline", "double breasted", "single breasted", "empire waist",
    "cinched waist", "cocoon", "trapeze", "bodycon", "cargo", "pleated", "culottes",
    "bermuda", "capri", "boxer short", "capsule",
)
_TREND_MATERIALS = (
    "faux fur", "patent leather", "suede", "leather", "denim", "linen", "silk", "satin",
    "velvet", "corduroy", "tweed", "wool", "merino", "cashmere", "mohair", "boucle",
    "crochet", "knit", "lace", "mesh", "sheer", "chiffon", "organza", "jersey", "poplin",
    "seersucker", "canvas", "shearling", "sequin", "sequins", "jacquard", "fringe",
)
_TREND_STYLES = (
    "animal print", "leopard print", "zebra print", "polka dot", "polka dots",
    "pinstripe", "plaid", "tartan", "checkered", "houndstooth", "gingham", "floral",
    "paisley", "tie dye", "colour blocking", "color blocking", "monochrome",
    "quiet luxury", "old money", "preppy", "boho", "bohemian", "minimalist",
    "maximalist", "athleisure", "normcore", "gorpcore", "coquette", "balletcore",
    "western", "y2k", "grunge", "punk", "romantic", "utilitarian", "streetwear",
    "retro", "vintage", "power dressing", "layering", "double denim", "matching set",
    "co ord", "embellished", "ruffles", "bows", "pearls", "platform", "kitten heel",
    "ballet flats", "loafers", "knee high boots", "slouchy boots", "mary janes",
    "leopard", "stripes", "striped",
)

_TREND_SCHEMA: dict[str, tuple[str, ...]] = {
    "colours": _TREND_COLOURS,
    "silhouettes": _TREND_SILHOUETTES,
    "materials": _TREND_MATERIALS,
    "styles & details": _TREND_STYLES,
}

# Longest-first alternation so "butter yellow" wins over "yellow" at the same
# position (a standalone "yellow" elsewhere still matches — that's correct).
_TREND_MATCHERS: dict[str, re.Pattern[str]] = {
    category: re.compile(
        r"\b(" + "|".join(sorted(map(re.escape, vocab), key=len, reverse=True)) + r")\b"
    )
    for category, vocab in _TREND_SCHEMA.items()
}

# A sentence mentioning any of these cues is talking about what's on the way
# OUT; its matched terms are reported as fading rather than trending.
_FADING_CUES = re.compile(
    r"\b(dated|out of (?:style|fashion)|out of favou?r|fading|declining|pass[eé]|"
    r"no longer|on the way out|falling out|losing (?:steam|ground)|retire[ds]?|skip)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")


def _dedupe(terms: list[str]) -> list[str]:
    return list(dict.fromkeys(terms))


def extract_trend_attributes(answer: str) -> dict[str, dict[str, list[str]]]:
    """Schema-validate a trend answer: allowlisted terms only, split by polarity.

    Returns ``{"trending": {category: [terms]}, "fading": {category: [terms]}}``
    with empty categories omitted. Anything in the answer that isn't in the
    allowlists — including any injected instructions — is discarded.
    """
    out: dict[str, dict[str, list[str]]] = {"trending": {}, "fading": {}}
    if not answer:
        return out
    for sentence in _SENTENCE_SPLIT.split(answer):
        normalized = sentence.lower().replace("-", " ")
        polarity = "fading" if _FADING_CUES.search(normalized) else "trending"
        for category, matcher in _TREND_MATCHERS.items():
            found = matcher.findall(normalized)
            if found:
                out[polarity][category] = _dedupe(out[polarity].get(category, []) + found)
    # A term named both ways in one answer stays only where it was last seen as
    # fading — "X is out" is the stronger, safer signal for styling advice.
    for category, fading_terms in out["fading"].items():
        trending = [t for t in out["trending"].get(category, []) if t not in fading_terms]
        if trending:
            out["trending"][category] = trending
        else:
            out["trending"].pop(category, None)
    return out


def _source_domains(result: dict[str, Any]) -> list[str]:
    """Source hostnames only — structured provenance, no free-text titles."""
    domains: list[str] = []
    for source in result.get("sources") or []:
        try:
            host = urlparse(source.get("url") or "").hostname
        except ValueError:
            continue
        if host:
            domains.append(host.removeprefix("www."))
    return _dedupe(domains)


def build_trend_block(result: dict[str, Any] | None) -> str:
    """Prompt block for the chat system prompt. "" when no trend context.

    Built exclusively from allowlist-validated vocabulary and source domains —
    the retrieved web prose itself never enters the prompt.
    """
    if not result:
        return ""
    attrs = extract_trend_attributes(result.get("answer") or "")
    lines: list[str] = []
    for category, terms in attrs["trending"].items():
        lines.append(f"- Currently trending {category}: {', '.join(terms)}")
    for category, terms in attrs["fading"].items():
        lines.append(f"- Considered dated/fading {category}: {', '.join(terms)}")
    if not lines:
        # Nothing survived schema validation — degrade to no trend context
        # rather than ever falling back to raw web prose.
        return ""
    domains = _source_domains(result)
    if domains:
        lines.append(f"Sources: {', '.join(domains)}")
    return "\n".join(
        [
            "\n[CURRENT FASHION TRENDS — LIVE WEB RESEARCH]",
            "Validated trend signals extracted from live web research:",
            *lines,
            "Use this only to inform styling advice and trend commentary. You must "
            "still recommend ONLY items that exist in the user's wardrobe context — "
            "never invent items to match a trend; if the closet can't achieve a "
            "trend, say so honestly.",
            "[END CURRENT FASHION TRENDS]",
        ]
    )
