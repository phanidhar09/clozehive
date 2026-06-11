"""
LLM Input Safety — sanitise user-controlled content before injection into prompts.

WHY THIS EXISTS
───────────────
User-supplied strings (item names, notes, trip descriptions, chat messages …)
may contain prompt-injection payloads.  Before any such value is embedded in a
system or user prompt it must pass through one of the sanitisers below.

USAGE
─────
    from app.core.llm_safety import sanitize_user_text, wrap_untrusted

    safe_name  = sanitize_user_text(item.name, max_len=100)
    safe_notes = sanitize_user_text(item.notes, max_len=500)

    # In the prompt itself, always wrap untrusted data in a clearly labelled block:
    system_prompt = (
        "You are a fashion stylist.\\n\\n"
        + wrap_untrusted("Wardrobe item notes", safe_notes)
    )

WHAT IS SANITISED
──────────────────
1. Injection marker patterns — e.g. "ignore previous instructions",
   "system:", "assistant:", "new system prompt", markdown fences used to
   escape context, etc.
2. Excessive whitespace / control characters.
3. Length — each field is capped so large payloads cannot dominate prompts.

WHAT IS PRESERVED
──────────────────
Ordinary fashion / travel language is left intact.  The sanitiser is not a
content filter — it does not remove profanity or off-topic text.
"""

from __future__ import annotations

import re
import unicodedata

# ── Compiled patterns ─────────────────────────────────────────────────────────

# Common prompt-injection openers (case-insensitive, match at word boundary)
_INJECTION_PATTERNS = re.compile(
    r"""
    (?ix)               # ignore case, verbose
    \b(
        ignore\s+(all\s+)?previous\s+(instructions?|prompts?|context) |
        disregard\s+.{0,30}instructions? |
        forget\s+(all\s+)?previous |
        act\s+as\s+(a\s+)?(?:DAN|jailbreak|evil|uncensored) |
        you\s+are\s+now |
        new\s+system\s+prompt |
        override\s+(the\s+)?system |
        # Explicit role markers that could break context parsing
        \[SYSTEM\] |
        <\s*system\s*> |
        <\s*/\s*system\s*> |
        \{SYSTEM\} |
        \{\{system\}\} |
        # Data-exfil markers
        print\s+(the\s+)?system\s+prompt |
        reveal\s+(your\s+)?instructions? |
        what\s+(are\s+)?your\s+(system\s+)?instructions? |
        # Jailbreak / persona override attempts
        pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(evil|malicious|unfiltered|unrestricted) |
        do\s+anything\s+now |
        developer\s+mode |
        jailbreak |
        # Instruction boundary smuggling
        --END\s+INSTRUCTIONS? |
        ###\s*END\s*INSTRUCTIONS? |
        \[END\s+SYSTEM\]
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Markdown code-fence abuse (triple backtick blocks intended to escape context)
_CODE_FENCE = re.compile(r"```[\s\S]{0,2000}?```", re.DOTALL)

# Runs of control characters (except standard whitespace)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Unicode bidirectional control characters — used for text direction spoofing attacks
# (e.g. right-to-left override can make "ignore instructions" invisible to reviewers)
_BIDI_CHARS = re.compile(r"[‪-‮⁦-⁩‏؜]")

# HTML/XML tags that could be used to inject fake context blocks or script execution
_HTML_TAGS = re.compile(
    r"<\s*/?\s*(script|style|template|iframe|object|embed|form|input|svg|meta|link|base)\b[^>]*>",
    re.IGNORECASE,
)

# Collapse 3+ consecutive newlines to 2
_EXCESS_NEWLINES = re.compile(r"\n{3,}")

# Collapse 3+ consecutive spaces/tabs to a single space
_EXCESS_SPACES = re.compile(r"[ \t]{3,}")

# Role-override prefixes that attempt to hijack message parsing
_ROLE_PREFIXES = re.compile(
    r"^(system|assistant|human|user|ai|bot)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)

# ── Default field length limits ───────────────────────────────────────────────

_DEFAULT_MAX_LEN = 2000  # generic upper bound
FIELD_LIMITS: dict[str, int] = {
    "name": 100,
    "category": 50,
    "color": 60,
    "brand": 80,
    "material": 100,
    "pattern": 80,
    "description": 800,
    "notes": 800,
    "activity": 200,
    "trip_notes": 600,
    "message": 2000,  # chat messages get a larger allowance
    "feedback": 500,
    "style_notes": 300,
}


# ── Core sanitiser ────────────────────────────────────────────────────────────


def sanitize_user_text(
    text: str | None,
    *,
    field: str = "generic",
    max_len: int | None = None,
) -> str:
    """Return a cleaned, length-capped version of *text*.

    Safe to call with ``None`` — returns ``""`` in that case.

    Args:
        text:    Raw user-supplied string.
        field:   Semantic field name used to look up default length limits
                 (see ``FIELD_LIMITS``).  Falls through to ``_DEFAULT_MAX_LEN``.
        max_len: Override the per-field limit if provided.
    """
    if not text:
        return ""

    # 1. Unicode normalise to NFC — handles homoglyph substitution tricks.
    value = unicodedata.normalize("NFC", str(text))

    # 2. Strip control characters.
    value = _CONTROL_CHARS.sub("", value)

    # 3. Strip Unicode bidirectional control characters (direction-spoofing attacks).
    value = _BIDI_CHARS.sub("", value)

    # 4. Remove HTML/XML tags used to inject fake context blocks.
    value = _HTML_TAGS.sub("[html removed]", value)

    # 5. Remove code-fence blocks (```) used to embed fake context.
    value = _CODE_FENCE.sub("[code removed]", value)

    # 6. Remove role-prefix overrides (e.g. "System: do X" at line start).
    value = _ROLE_PREFIXES.sub("", value)

    # 7. Replace injection-opener phrases with a neutral placeholder.
    value = _INJECTION_PATTERNS.sub("[redacted]", value)

    # 8. Normalise whitespace.
    value = _EXCESS_NEWLINES.sub("\n\n", value)
    value = _EXCESS_SPACES.sub(" ", value)
    value = value.strip()

    # 7. Enforce length cap.
    limit = max_len if max_len is not None else FIELD_LIMITS.get(field, _DEFAULT_MAX_LEN)
    if len(value) > limit:
        value = value[:limit].rstrip() + "…"

    return value


def sanitize_list(
    items: list[str] | None,
    *,
    field: str = "generic",
    max_len: int | None = None,
    max_items: int = 20,
) -> list[str]:
    """Sanitise each element of a list.  Returns an empty list for falsy input."""
    if not items:
        return []
    return [sanitize_user_text(item, field=field, max_len=max_len) for item in items[:max_items] if item]


# ── Prompt construction helpers ───────────────────────────────────────────────


def wrap_untrusted(label: str, content: str) -> str:
    """Wrap sanitised user content in a clearly labelled block.

    This makes the boundary between trusted instructions and untrusted data
    explicit to the model, reducing the chance that injected text is treated
    as an instruction.

    Example output::

        [USER DATA: Wardrobe item notes]
        Blue linen shirt, casual style
        [END USER DATA]
    """
    if not content:
        return ""
    safe_label = sanitize_user_text(label, field="name", max_len=80)
    return f"[USER DATA: {safe_label}]\n{content}\n[END USER DATA]"


def build_closet_item_summary(item: dict) -> str:
    """Return a single sanitised line describing a closet item for prompt injection."""
    name = sanitize_user_text(item.get("name", ""), field="name")
    category = sanitize_user_text(item.get("category", ""), field="category")
    color = sanitize_user_text(item.get("color", ""), field="color")
    fabric = sanitize_user_text(item.get("fabric") or item.get("material", ""), field="material")
    occasion = sanitize_user_text(str(item.get("occasion") or ""), field="notes", max_len=80)
    season = sanitize_user_text(str(item.get("season") or ""), field="notes", max_len=60)
    return (
        f"{name} | {category} | color={color} | fabric={fabric} "
        f"| occasion={occasion} | season={season} | worn={item.get('wear_count', 0)}x"
    )
