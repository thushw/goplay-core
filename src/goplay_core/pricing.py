"""Approximate USD cost estimation from Claude API token usage.

The Messages API returns token counts (see `usage` on a response) but
never a dollar figure -- cost has to be computed from those counts and
the per-model price list below. This is necessarily a snapshot: update
PRICING_PER_MTOK when Anthropic's pricing changes.

Prices are USD per 1,000,000 tokens, as (input, output). Cache writes
are billed at ~1.25x the input price, cache reads at ~0.1x -- see
https://platform.claude.com/docs/en/about-claude/pricing
"""

CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1

# (input_price, output_price) per 1M tokens. Keyed by model ID prefix so
# both bare IDs (e.g. "claude-haiku-4-5") and dated snapshots (e.g.
# "claude-3-haiku-20240307") resolve correctly.
PRICING_PER_MTOK = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # Older/dated snapshots this engine may still resolve to (e.g. the
    # _get_active_haiku_model() fallback, or an org pinned to an older
    # model list).
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-5-haiku": (0.80, 4.00),
}


def estimate_cost_usd(model: str, usage) -> float | None:
    """Estimate the USD cost of one API call from its `usage` object.

    Returns None if `model` doesn't match any known price entry --
    callers should log that case rather than silently reporting $0.
    """
    pricing = None
    for prefix, prices in PRICING_PER_MTOK.items():
        if model.startswith(prefix):
            pricing = prices
            break
    if pricing is None:
        return None

    input_price, output_price = pricing
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_write_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0

    cost = (
        input_tokens * input_price
        + cache_write_tokens * input_price * CACHE_WRITE_MULTIPLIER
        + cache_read_tokens * input_price * CACHE_READ_MULTIPLIER
        + output_tokens * output_price
    ) / 1_000_000
    return cost
