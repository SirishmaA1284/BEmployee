"""Agent workflow tests (tests/agents/).

These drive the full LangGraph workflows through the registry with a
scripted MockProvider (ADR-005), against the real test database — so the
agent's tool-call sequence, the deterministic services, and the verification
step are all exercised end-to-end without any network/LLM dependency.
"""

import uuid

import pytest

from app.agents.orchestrator import run_agent
from app.core.llm.mock import MockProvider
from app.models.agent import AgentSession, AgentTask
from app.models.enums import AgentSessionStatus, AgentTaskStatus, BusinessRole


async def _new_user_and_task(client, business_id, db_session) -> tuple[str, str, str]:
    """Registers a fresh user (returns (token, user_id)) and creates a
    session+task row so registry-recorded actions have valid FKs.
    """
    register = await client.post(
        "/api/auth/register",
        json={"email": f"agent-{uuid.uuid4().hex[:8]}@example.com", "password": "a-strong-password", "full_name": "Agent Tester"},
    )
    user_id = register.json()["user"]["id"]
    token = register.json()["access_token"]

    session = AgentSession(
        business_id=business_id,
        user_id=uuid.UUID(user_id),
        status=AgentSessionStatus.RUNNING,
        user_message="test",
    )
    db_session.add(session)
    await db_session.flush()
    task = AgentTask(session_id=session.id, status=AgentTaskStatus.RUNNING)
    db_session.add(task)
    await db_session.flush()
    return token, user_id, str(task.id)


async def _seed_customer_and_product(client, headers, sku="COFFEE-500", name="Coffee 500g", price="250.00", qty=10):
    customer = (
        await client.post("/api/customers", json={"name": "Rahul"}, headers=headers)
    ).json()
    product = (
        await client.post(
            "/api/products",
            json={"sku": sku, "name": name, "unit_price": price},
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": qty}, headers=headers
    )
    return customer, product


async def _seed_supplier(client, headers, name, product_id, price, lead_time_days=3):
    supplier = (await client.post("/api/suppliers", json={"name": name}, headers=headers)).json()
    await client.post(
        f"/api/suppliers/{supplier['id']}/products",
        json={"product_id": product_id, "price": price, "lead_time_days": lead_time_days},
        headers=headers,
    )
    return supplier


async def _run(provider, db_session, business_id, user_id, task_id, message, role=BusinessRole.OWNER):
    return await run_agent(
        provider,
        db_session,
        business_id=business_id,
        user_id=uuid.UUID(user_id),
        role=role,
        task_id=uuid.UUID(task_id),
        message=message,
    )


async def test_order_workflow_end_to_end(client, business, db_session):
    headers = business["owner_headers"]
    _, product = await _seed_customer_and_product(client, headers)
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_ORDER", "summary": "Create an order"}},
            {
                "tool": "extract_order",
                "arguments": {
                    "customer_query": "Rahul",
                    "items": [{"product_query": "coffee", "quantity": 3}],
                },
            },
        ]
    )
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "Create an order for Rahul with 3 coffee packets",
    )

    assert state["verified"] is True
    assert "Invoice" in state["reply"]
    order = state["result"]
    assert order["total"] == "750.00"
    assert len(order["items"]) == 1

    tool_results = state["tool_results"]
    assert tool_results["search_customers"]["ok"] is True
    assert tool_results["search_products"]["ok"] is True
    assert tool_results["create_order"]["data"]["invoice_number"] == "INV-000001"
    assert tool_results["get_order"]["ok"] is True

    inv = (await client.get(f"/api/inventory/{product['id']}", headers=headers)).json()
    assert inv["quantity_on_hand"] == 7


async def test_order_workflow_unknown_product_returns_helpful_error(client, business, db_session):
    headers = business["owner_headers"]
    await _seed_customer_and_product(client, headers)
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_ORDER", "summary": "Create an order"}},
            {
                "tool": "extract_order",
                "arguments": {
                    "customer_query": "Rahul",
                    "items": [{"product_query": "television", "quantity": 1}],
                },
            },
        ]
    )
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "Create an order for Rahul with 1 television",
    )
    assert "No product matches 'television'" in state["reply"]


async def test_low_stock_workflow(client, business, db_session):
    headers = business["owner_headers"]
    low_product = (
        await client.post(
            "/api/products",
            json={"sku": "SUGAR-1", "name": "Sugar 1kg", "unit_price": "60.00"},
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/inventory/{low_product['id']}/adjust", json={"change_quantity": 2}, headers=headers
    )
    await client.patch(
        f"/api/products/{low_product['id']}",
        json={"reorder_threshold": 5, "reorder_quantity": 20},
        headers=headers,
    )
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider(
        script=[{"tool": "classify_intent", "arguments": {"intent": "LOW_STOCK", "summary": "List low stock"}}]
    )
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "Which products are running low?",
    )
    assert "Sugar 1kg" in state["reply"]
    assert state["result"]["low_stock"][0]["sku"] == "SUGAR-1"


async def test_compare_suppliers_workflow(client, business, db_session):
    headers = business["owner_headers"]
    _, product = await _seed_customer_and_product(client, headers, qty=0)
    await _seed_supplier(client, headers, "Metro", product["id"], "220.00", lead_time_days=2)
    await _seed_supplier(client, headers, "Kirana", product["id"], "210.00", lead_time_days=5)
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "COMPARE_SUPPLIERS", "summary": "Compare offers"}},
            {"tool": "extract_product_query", "arguments": {"query": "coffee"}},
        ]
    )
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "Which supplier gives the best price for coffee?",
    )
    assert "Kirana at 210.00" in state["reply"]
    assert state["result"]["offers"][0]["supplier_name"] == "Kirana"


async def test_create_purchase_order_direct(client, business, db_session):
    headers = business["owner_headers"]
    _, product = await _seed_customer_and_product(client, headers, qty=0)
    await _seed_supplier(client, headers, "Metro", product["id"], "200.00")
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_PURCHASE_ORDER", "summary": "PO"}},
            {
                "tool": "extract_purchase_order",
                "arguments": {
                    "supplier_query": "Metro",
                    "items": [{"product_query": "coffee", "quantity": 5}],
                },
            },
        ]
    )
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "Prepare a purchase order from Metro for 5 coffee packets",
    )
    assert state["verified"] is True
    assert "Purchase order" in state["reply"]
    po_id = state["result"]["purchase_order_id"]

    po = (await client.get(f"/api/purchase-orders/{po_id}", headers=headers)).json()
    assert po["status"] == "DRAFT"
    assert po["total"] == "1000.00"


async def test_create_purchase_order_low_stock_driven(client, business, db_session):
    """'Prepare a PO for everything likely to run out' — the workflow picks
    the low-stock products and the supplier that wins the most products.
    """
    headers = business["owner_headers"]
    _, coffee = await _seed_customer_and_product(client, headers, sku="COFFEE-500", qty=0)
    sugar = (
        await client.post(
            "/api/products", json={"sku": "SUGAR-1", "name": "Sugar 1kg", "unit_price": "60.00"}, headers=headers
        )
    ).json()
    await client.post(f"/api/inventory/{sugar['id']}/adjust", json={"change_quantity": 0}, headers=headers)

    for product, reorder_qty in ((coffee, 10), (sugar, 20)):
        await client.patch(
            f"/api/products/{product['id']}",
            json={"reorder_threshold": 1, "reorder_quantity": reorder_qty},
            headers=headers,
        )
    # Metro is cheapest for coffee only; Kirana cheapest for sugar only.
    await _seed_supplier(client, headers, "Metro", coffee["id"], "200.00")
    await _seed_supplier(client, headers, "Metro", sugar["id"], "55.00")
    await _seed_supplier(client, headers, "Kirana", coffee["id"], "250.00")
    await _seed_supplier(client, headers, "Kirana", sugar["id"], "45.00")
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider(
        script=[
            {"tool": "classify_intent", "arguments": {"intent": "CREATE_PURCHASE_ORDER", "summary": "PO"}},
            {"tool": "extract_purchase_order", "arguments": {"supplier_query": None, "items": []}},
        ]
    )
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "Prepare a purchase order for everything likely to run out",
    )
    assert state["verified"] is True
    # Each product is cheapest at a different supplier, so each wins once —
    # the tie is broken by name: Kirana < Metro alphabetically.
    po_id = state["result"]["purchase_order_id"]
    po = (await client.get(f"/api/purchase-orders/{po_id}", headers=headers)).json()
    assert len(po["items"]) == 1
    assert po["items"][0]["quantity"] == 20
    assert po["items"][0]["unit_cost"] == "45.00"


async def test_sales_report_workflow(client, business, db_session):
    headers = business["owner_headers"]
    await _seed_customer_and_product(client, headers, qty=10)
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider(
        script=[{"tool": "classify_intent", "arguments": {"intent": "SALES_REPORT", "summary": "Report"}}]
    )
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "Give me a sales report",
    )
    assert "0 order(s)" in state["reply"]


async def test_unrecognized_request_routes_to_clarify(client, business, db_session):
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)
    provider = MockProvider(
        script=[{"tool": "classify_intent", "arguments": {"intent": "UNKNOWN", "summary": "n/a"}}]
    )
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "What is the weather?",
    )
    assert "I couldn't work out" in state["reply"]


@pytest.mark.asyncio
async def test_agent_step_limit_is_enforced(client, business, db_session, monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("MAX_AGENT_STEPS", "0")
    _, user_id, task_id = await _new_user_and_task(client, business["business_id"], db_session)

    provider = MockProvider()
    state = await _run(
        provider, db_session, business["business_id"], user_id, task_id,
        "Which products are running low?",
    )
    assert "Exceeded max agent steps" in state["reply"]

    # Restore the env var BEFORE clearing the cache, so the next test's
    # get_settings() re-reads the real configuration.
    monkeypatch.undo()
    get_settings.cache_clear()