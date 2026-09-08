"""Deterministic policy engine (docs/decisions.md ADR-004, FR-16/FR-17).

The LLM proposes *what* to do; whether it is risky — and therefore whether
it needs a human approval — is decided here in plain Python from the
business's configured policies. This module cannot be short-circuited by
prompt content.

Responsibilities:
- Load a business's active policies (business_policies rows).
- Compute the *projected* money impact of a proposed write so a
  MONEY_THRESHOLD policy can escalate MEDIUM -> HIGH before execution.
- Combine a tool's declared risk level with the policy evaluation to
  produce the final risk class used by the registry and the approval
  pipeline.

`classify_action` (in app/policies/risk.py) remains the pure, synchronous
tool-declared classification (Phase 4 behavior, unit-tested directly).
`evaluate_risk` here is the async, policy-aware classification the registry
and approval pipeline actually call.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_policy import BusinessPolicy
from app.models.enums import PolicyType
from app.models.product import Product
from app.models.supplier_product import SupplierProduct
from app.policies.risk import RiskLevel, classify_action

if TYPE_CHECKING:
    from app.tools.base import ToolSpec

# Money-impact tools: their projected impact is what a MONEY_THRESHOLD
# policy compares against. Kept explicit so only genuinely money-changing
# actions are escalated.
_MONEY_TOOLS = {"create_order", "create_purchase_order"}


async def get_active_policies(db: AsyncSession, business_id: uuid.UUID) -> list[BusinessPolicy]:
    result = await db.execute(
        select(BusinessPolicy).where(
            BusinessPolicy.business_id == business_id, BusinessPolicy.is_active.is_(True)
        )
    )
    return list(result.scalars().all())


def money_threshold(policies: list[BusinessPolicy]) -> Decimal | None:
    """Returns the smallest active MONEY_THRESHOLD amount, or None."""
    amounts = []
    for policy in policies:
        if policy.policy_type == PolicyType.MONEY_THRESHOLD and policy.is_active:
            try:
                amounts.append(Decimal(str(policy.value["amount"])))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
    if not amounts:
        return None
    return min(amounts)


async def compute_money_impact(
    db: AsyncSession, business_id: uuid.UUID, tool_name: str, arguments: dict
) -> Decimal | None:
    """Projected money impact of a proposed write, for threshold comparison.

    Returns None for non-money tools or when impact cannot be computed
    (unknown ids). Deterministic backend math only (Rule 4).
    """
    if tool_name == "create_order":
        total = Decimal("0")
        for item in arguments.get("items", []):
            product_result = await db.execute(
                select(Product).where(
                    Product.id == uuid.UUID(str(item["product_id"])),
                    Product.business_id == business_id,
                    Product.deleted_at.is_(None),
                )
            )
            product = product_result.scalar_one_or_none()
            if product is None:
                return None
            total += product.unit_price * int(item["quantity"])
        return total

    if tool_name == "create_purchase_order":
        total = Decimal("0")
        supplier_id = uuid.UUID(str(arguments.get("supplier_id")))
        for item in arguments.get("items", []):
            product_id = uuid.UUID(str(item["product_id"]))
            quantity = int(item["quantity"])
            unit_cost = item.get("unit_cost")
            if unit_cost is None:
                sp_result = await db.execute(
                    select(SupplierProduct).where(
                        SupplierProduct.supplier_id == supplier_id,
                        SupplierProduct.product_id == product_id,
                    )
                )
                sp = sp_result.scalar_one_or_none()
                if sp is None:
                    return None
                total += sp.price * quantity
            else:
                total += Decimal(str(unit_cost)) * quantity
        return total

    return None


async def evaluate_risk(
    db: AsyncSession,
    business_id: uuid.UUID,
    tool: ToolSpec,
    arguments: dict,
) -> RiskLevel:
    """Policy-aware risk classification.

    Starts from the tool's declared risk (classify_action). For money tools,
    if an active MONEY_THRESHOLD policy exists and the projected impact
    meets/exceeds it, MEDIUM is escalated to HIGH (always requires approval).
    LOW reads are never escalated.
    """
    risk = classify_action(tool, arguments)
    if risk != RiskLevel.MEDIUM:
        return risk
    if tool.name not in _MONEY_TOOLS:
        return risk
    policies = await get_active_policies(db, business_id)
    threshold = money_threshold(policies)
    if threshold is None:
        return risk
    impact = await compute_money_impact(db, business_id, tool.name, arguments)
    if impact is not None and impact >= threshold:
        return RiskLevel.HIGH
    return risk


def approval_roles_for(policies: list[BusinessPolicy], risk_level: RiskLevel) -> list[str]:
    """Which roles may resolve an approval request at a given risk level.

    Defaults to OWNER/ADMIN when no APPROVAL_ROLES policy is configured
    (docs/authorization.md). A per-business policy can override, e.g. to let
    EMPLOYEE approve MEDIUM-risk actions.
    """
    for policy in policies:
        if policy.policy_type != PolicyType.APPROVAL_ROLES:
            continue
        roles = policy.value.get("roles")
        if isinstance(roles, list):
            return [str(r) for r in roles]
    return ["OWNER", "ADMIN"]
