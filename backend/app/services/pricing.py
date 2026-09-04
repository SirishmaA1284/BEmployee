"""Deterministic money math. Never delegated to the LLM (spec Rule 4) — the
agent layer (Phase 4) calls these same functions instead of asking a model
to compute totals.
"""

from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")


def line_total(quantity: int, unit_price: Decimal) -> Decimal:
    return (Decimal(quantity) * unit_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def sum_amounts(amounts: list[Decimal]) -> Decimal:
    total = sum(amounts, Decimal("0.00"))
    return total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def compute_tax(subtotal: Decimal) -> Decimal:
    """MVP has no tax engine (docs/decisions.md ADR-014) — always zero,
    kept as a real function (not a hardcoded 0 scattered at call sites) so
    a future tax rule has exactly one place to change.
    """
    return Decimal("0.00")
