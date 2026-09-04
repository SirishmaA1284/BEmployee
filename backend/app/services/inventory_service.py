"""Deterministic inventory math. See app/services/pricing.py for why this
lives in plain functions instead of being inferred by an LLM.
"""


def is_stock_sufficient(quantity_on_hand: int, requested_quantity: int) -> bool:
    return quantity_on_hand >= requested_quantity


def is_low_stock(quantity_on_hand: int, reorder_threshold: int) -> bool:
    return quantity_on_hand <= reorder_threshold
