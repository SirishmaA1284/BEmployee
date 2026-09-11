"""Inline customer creation tests (Phase 10).

A customer no longer blocks an order: the agent auto-creates unknown
customers (deduped) and the REST API accepts an inline `customer` object.
Repeat orders reuse the same customer instead of duplicating rows.
"""

import uuid


async def _seed_stocked_product(client, headers):
    product = (
        await client.post(
            "/api/products", json={"sku": "COFFEE-500", "name": "Coffee 500g", "unit_price": "250.00"}, headers=headers
        )
    ).json()
    await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": 10}, headers=headers
    )
    return product


async def _chat_order(client, headers, message):
    return (
        await client.post(
            "/api/agent/chat",
            json={"message": message},
            headers=headers,
        )
    ).json()


async def test_agent_creates_unknown_customer_and_orders(client, business):
    """'Create an order for <new customer>' just works: the customer is added
    automatically and the order completes."""
    headers = business["owner_headers"]
    await _seed_stocked_product(client, headers)

    session = await _chat_order(
        client, headers, "Create an order for Meera with 3 coffee packets"
    )
    assert session["status"] == "COMPLETED", session
    assert "Meera" in session["reply"]
    assert "new customer" in session["reply"]

    customers = (await client.get("/api/customers", headers=headers)).json()
    assert [c["name"] for c in customers] == ["Meera"]

    orders = (await client.get("/api/orders", headers=headers)).json()
    assert len(orders) == 1
    assert orders[0]["customer_name"] == "Meera"


async def test_agent_reuses_existing_customer(client, business):
    """A repeat order for the same new customer does not create a duplicate."""
    headers = business["owner_headers"]
    await _seed_stocked_product(client, headers)
    await _chat_order(client, headers, "Create an order for Meera with 3 coffee packets")
    await _chat_order(client, headers, "Create an order for Meera with 1 coffee packet")

    customers = (await client.get("/api/customers", headers=headers)).json()
    assert len(customers) == 1

    orders = (await client.get("/api/orders", headers=headers)).json()
    assert len(orders) == 2
    assert {o["customer_name"] for o in orders} == {"Meera"}


async def test_agent_still_uses_existing_customer_without_creating(client, business):
    """Existing customers keep working and are not re-created."""
    headers = business["owner_headers"]
    customer = (await client.post("/api/customers", json={"name": "Rahul"}, headers=headers)).json()
    await _seed_stocked_product(client, headers)

    session = await _chat_order(client, headers, "Create an order for Rahul with 3 coffee packets")
    assert session["status"] == "COMPLETED", session
    assert "new customer" not in session["reply"]

    customers = (await client.get("/api/customers", headers=headers)).json()
    assert len(customers) == 1
    assert customers[0]["id"] == customer["id"]


async def test_rest_order_with_inline_customer(client, business):
    headers = business["owner_headers"]
    product = await _seed_stocked_product(client, headers)

    resp = await client.post(
        "/api/orders",
        json={
            "customer": {"name": "Priya", "phone": "+91 98765 43210"},
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["customer_name"] == "Priya"

    customers = (await client.get("/api/customers", headers=headers)).json()
    assert [c["name"] for c in customers] == ["Priya"]
    assert customers[0]["phone"] == "+91 98765 43210"


async def test_rest_inline_customer_dedupes_by_name(client, business):
    headers = business["owner_headers"]
    product = await _seed_stocked_product(client, headers)

    await client.post(
        "/api/orders",
        json={"customer": {"name": "Priya"}, "items": [{"product_id": product["id"], "quantity": 1}]},
        headers=headers,
    )
    resp = await client.post(
        "/api/orders",
        json={"customer": {"name": "priya"}, "items": [{"product_id": product["id"], "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 201

    customers = (await client.get("/api/customers", headers=headers)).json()
    assert len(customers) == 1  # case-insensitive name match reused the row


async def test_rest_order_requires_exactly_one_customer(client, business):
    headers = business["owner_headers"]
    product = await _seed_stocked_product(client, headers)
    items = [{"product_id": product["id"], "quantity": 1}]

    both = await client.post(
        "/api/orders",
        json={"customer_id": str(uuid.uuid4()), "customer": {"name": "X"}, "items": items},
        headers=headers,
    )
    assert both.status_code == 422

    neither = await client.post("/api/orders", json={"items": items}, headers=headers)
    assert neither.status_code == 422


async def test_unknown_customer_id_still_404(client, business):
    """Giving a customer_id that does not exist is still an error — only the
    inline `customer` object auto-creates."""
    headers = business["owner_headers"]
    product = await _seed_stocked_product(client, headers)
    resp = await client.post(
        "/api/orders",
        json={"customer_id": str(uuid.uuid4()), "items": [{"product_id": product["id"], "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 404