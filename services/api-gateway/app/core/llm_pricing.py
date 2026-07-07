"""LLM pricing table + cost computation (USD).

Prices are per 1,000,000 tokens, sourced from OpenAI's public pricing. Kept as a
single module constant so cost math lives in exactly one place — update here when
pricing changes. An unknown model falls back to the strong-model rate so spend is
never silently *under*-counted (better to over-estimate than to under-report cost).
"""

from __future__ import annotations

# model -> (prompt_usd_per_1M, completion_usd_per_1M)
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    # Embedding models have no completion tokens; completion rate is 0.
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    # Gemini (Google public pricing) — used by the vision detection pass.
    # Without these, Gemini calls would be over-counted at the gpt-4o fallback rate.
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-1.5-flash": (0.075, 0.30),
}

# Fallback for unrecognised models — bias toward the strong model so cost is
# never undercounted for a model we forgot to add.
_DEFAULT = _PRICING["gpt-4o"]


def _rates(model: str) -> tuple[float, float]:
    key = (model or "").strip().lower()
    if key in _PRICING:
        return _PRICING[key]
    # Dated/suffixed ids (e.g. "gpt-4o-2024-08-06") — match the longest prefix.
    best: tuple[str, tuple[float, float]] | None = None
    for name, rate in _PRICING.items():
        if key.startswith(name) and (best is None or len(name) > len(best[0])):
            best = (name, rate)
    return best[1] if best else _DEFAULT


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> tuple[float, float, float]:
    """Return ``(input_cost, output_cost, total_cost)`` in USD for one call."""
    p_rate, c_rate = _rates(model)
    input_cost = (max(prompt_tokens, 0) / 1_000_000) * p_rate
    output_cost = (max(completion_tokens, 0) / 1_000_000) * c_rate
    return input_cost, output_cost, input_cost + output_cost
