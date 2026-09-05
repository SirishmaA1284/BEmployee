"""Verification Agent (FR-19).

After a workflow executes a state-changing action, a verification node
re-reads the affected state through the registry (never direct queries) and
checks it matches the intended outcome. Failed verification marks the task
failed and surfaces a message; it never silently passes.

Phase 4 checks are deterministic equality checks against the data the
workflow just wrote (line totals, status, invoice presence). Deeper
cross-checking (e.g. independent re-computation from raw inputs) extends
this module in later phases — keep new checks here, not in the workflows.

LangGraph node rule: helpers return their findings as plain values; the
workflow nodes decide what to merge into state.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runner import run_tool
from app.agents.state import AgentState


def _money(value: str) -> Decimal:
    return Decimal(value or "0")


def verify_order_totals(order: dict[str, Any]) -> list[str]:
    """Re-computes line totals from the stored order and checks the header
    math matches. Returns a list of problems (empty = verified).
    """
    problems = []
    subtotal = sum(_money(line["line_total"]) for line in order["items"])
    if _money(order["subtotal"]) != subtotal:
        problems.append(f"subtotal {order['subtotal']} != sum of line totals {subtotal}")
    if _money(order["tax_amount"]) != Decimal("0.00"):
        problems.append(f"unexpected tax amount {order['tax_amount']}")
    if _money(order["total"]) != _money(order["subtotal"]):
        problems.append(f"total {order['total']} != subtotal {order['subtotal']}")
    if order.get("invoice_number") is None:
        problems.append("no invoice was generated")
    return problems


async def verify_created_order(state: AgentState, db: AsyncSession) -> list[str]:
    """Re-reads the order after creation and checks it (FR-19). Returns a
    list of verification problems (empty = verified).
    """
    result = await run_tool(state, db, "get_order", {"order_id": state["created_order_id"]})
    if not result.get("ok"):
        return [f"could not re-read the order ({result.get('error')})"]
    return verify_order_totals(result["data"])