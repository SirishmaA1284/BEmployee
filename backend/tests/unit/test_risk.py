"""Risk classification seam tests (docs/decisions.md ADR-004). Phase 4:
a tool's declared risk level is the classification; Phase 5 adds policy
evaluation behind the same function."""

import pytest

from app.models.enums import BusinessRole
from app.policies.risk import RiskLevel, classify_action
from app.tools.base import ToolSpec
from app.tools.registry import registry


@pytest.mark.asyncio
async def test_read_tools_are_low_risk():
    for name in (
        "search_products",
        "get_product",
        "search_customers",
        "check_stock",
        "list_low_stock",
        "compare_supplier_prices",
        "search_suppliers",
        "list_orders",
        "get_order",
        "list_purchase_orders",
        "get_sales_report",
    ):
        tool = registry.get(name)
        assert tool is not None, name
        assert tool.risk_level == RiskLevel.LOW, name
        assert tool.required_roles is None, name


@pytest.mark.asyncio
async def test_write_tools_are_medium_risk():
    assert registry.get("create_order").risk_level == RiskLevel.MEDIUM
    assert registry.get("create_purchase_order").risk_level == RiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_create_purchase_order_restricted_to_owner_admin():
    tool = registry.get("create_purchase_order")
    assert tool.required_roles == (BusinessRole.OWNER, BusinessRole.ADMIN)


@pytest.mark.asyncio
async def test_classify_action_returns_tool_risk_level():
    tool = registry.get("create_order")
    assert classify_action(tool, {"customer_id": "x", "items": []}) == RiskLevel.MEDIUM
    tool = registry.get("check_stock")
    assert classify_action(tool, {"search": "coffee"}) == RiskLevel.LOW