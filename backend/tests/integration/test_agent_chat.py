"""Agent chat API integration tests (FR-11/FR-14/FR-15).

The default provider in tests is the MockProvider (openai-without-key falls
back to it), so the whole chat flow runs deterministically against the real
database: classify -> workflow -> tools -> verification -> persisted
session/task/actions.
"""

import uuid

from httpx import AsyncClient


async def _seed(client, headers, sku="COFFEE-500", name="Coffee 500g", price="250.00", qty=10):
    customer = (await client.post("/api/customers", json={"name": "Rahul"}, headers=headers)).json()
    product = (
        await client.post(
            "/api/products", json={"sku": sku, "name": name, "unit_price": price}, headers=headers
        )
    ).json()
    await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": qty}, headers=headers
    )
    return customer, product


async def test_chat_creates_order_and_persists_audit_trail(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    customer, product = await _seed(client, headers)

    response = await client.post("/api/agent/chat", json={"message": "Create an order for Rahul with 3 coffee packets"}, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["intent"] == "CREATE_ORDER"
    assert data["status"] == "COMPLETED"
    assert "Invoice" in data["reply"]
    assert data["result"]["total"] == "750.00"

    # Order actually exists and stock decremented.
    order = (await client.get(f"/api/orders/{data['result']['order_id']}", headers=headers)).json()
    assert order["status"] == "CONFIRMED"
    inv = (await client.get(f"/api/inventory/{product['id']}", headers=headers)).json()
    assert inv["quantity_on_hand"] == 7

    # Session list shows it; detail shows the task and every tool action.
    sessions = (await client.get("/api/agent/sessions", headers=headers)).json()
    assert sessions[0]["id"] == data["session_id"]
    assert sessions[0]["intent"] == "CREATE_ORDER"

    detail = (await client.get(f"/api/agent/sessions/{data['session_id']}", headers=headers)).json()
    assert len(detail["tasks"]) == 1
    assert detail["tasks"][0]["agent_name"] == "order"
    tool_names = [a["tool_name"] for a in detail["tasks"][0]["actions"]]
    assert tool_names == ["search_customers", "search_products", "create_order", "get_order"]

    create_action = detail["tasks"][0]["actions"][2]
    assert create_action["status"] == "SUCCESS"
    assert create_action["risk_level"] == "MEDIUM"
    assert create_action["input_summary"]["customer_id"] == customer["id"]


async def test_chat_low_stock(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = (
        await client.post(
            "/api/products", json={"sku": "SUGAR-1", "name": "Sugar 1kg", "unit_price": "60.00"}, headers=headers
        )
    ).json()
    await client.post(f"/api/inventory/{product['id']}/adjust", json={"change_quantity": 1}, headers=headers)
    await client.patch(f"/api/products/{product['id']}", json={"reorder_threshold": 5}, headers=headers)

    response = await client.post("/api/agent/chat", json={"message": "Which products are running low?"}, headers=headers)
    data = response.json()
    assert data["intent"] == "LOW_STOCK"
    assert data["status"] == "COMPLETED"
    assert "Sugar 1kg" in data["reply"]
    assert data["result"]["low_stock"][0]["sku"] == "SUGAR-1"


async def test_chat_compare_suppliers(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    _, product = await _seed(client, headers, qty=0)
    for name, price in (("Metro", "220.00"), ("Kirana", "210.00")):
        supplier = (await client.post("/api/suppliers", json={"name": name}, headers=headers)).json()
        await client.post(
            f"/api/suppliers/{supplier['id']}/products",
            json={"product_id": product["id"], "price": price, "lead_time_days": 3},
            headers=headers,
        )

    response = await client.post(
        "/api/agent/chat", json={"message": "Which supplier gives the best price for coffee?"}, headers=headers
    )
    data = response.json()
    assert data["intent"] == "COMPARE_SUPPLIERS"
    assert "Kirana at 210.00" in data["reply"]
    assert data["result"]["offers"][0]["supplier_name"] == "Kirana"


async def test_chat_sales_report_and_search(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    await _seed(client, headers)

    report = (await client.post("/api/agent/chat", json={"message": "Give me a sales report"}, headers=headers)).json()
    assert report["intent"] == "SALES_REPORT"
    assert "0 order(s)" in report["reply"]

    search = (await client.post("/api/agent/chat", json={"message": "search for products containing coffee"}, headers=headers)).json()
    assert search["intent"] == "SEARCH_PRODUCTS"
    assert "Coffee 500g" in search["reply"]


async def test_chat_unknown_message_needs_clarification(client: AsyncClient, business: dict):
    response = await client.post("/api/agent/chat", json={"message": "What is the weather?"}, headers=business["owner_headers"])
    data = response.json()
    assert data["intent"] == "UNKNOWN"
    assert data["status"] == "NEEDS_CLARIFICATION"
    assert "couldn't work out" in data["reply"]


async def test_employee_cannot_create_purchase_order_via_chat(client: AsyncClient, business: dict, employee_headers: dict):
    headers = business["owner_headers"]
    _, product = await _seed(client, headers, qty=0)
    supplier = (await client.post("/api/suppliers", json={"name": "Metro"}, headers=headers)).json()
    await client.post(
        f"/api/suppliers/{supplier['id']}/products",
        json={"product_id": product["id"], "price": "200.00", "lead_time_days": 2},
        headers=headers,
    )

    response = await client.post(
        "/api/agent/chat",
        json={"message": "Prepare a purchase order from Metro for 5 coffee packets"},
        headers=employee_headers,
    )
    data = response.json()
    assert data["status"] == "FAILED"
    assert "requires role" in data["reply"]

    pos = (await client.get("/api/purchase-orders", headers=headers)).json()
    assert pos == []


async def test_employee_can_create_order_via_chat(client: AsyncClient, business: dict, employee_headers: dict):
    customer, _ = await _seed(client, business["owner_headers"])
    response = await client.post(
        "/api/agent/chat",
        json={"message": "Create an order for Rahul with 3 coffee packets"},
        headers=employee_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


async def test_chat_sessions_are_tenant_isolated(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    await client.post("/api/agent/chat", json={"message": "Which products are running low?"}, headers=headers)
    session_id = (await client.get("/api/agent/sessions", headers=headers)).json()[0]["id"]

    # A user from another business cannot see or read this session.
    outsider_register = await client.post(
        "/api/auth/register",
        json={"email": f"outsider-{uuid.uuid4().hex[:8]}@example.com", "password": "a-strong-password", "full_name": "Outsider"},
    )
    outsider_token = outsider_register.json()["access_token"]
    outsider_business = await client.post(
        "/api/businesses", json={"name": "Other Business"}, headers={"Authorization": f"Bearer {outsider_token}"}
    )
    outsider_headers = {
        "Authorization": f"Bearer {outsider_token}",
        "X-Business-Id": outsider_business.json()["id"],
    }

    list_response = await client.get("/api/agent/sessions", headers=outsider_headers)
    assert list_response.json() == []

    detail_response = await client.get(f"/api/agent/sessions/{session_id}", headers=outsider_headers)
    assert detail_response.status_code == 404


async def test_chat_requires_business_context(client: AsyncClient, business: dict):
    token = business["owner_token"]
    response = await client.post(
        "/api/agent/chat", json={"message": "Which products are running low?"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 400