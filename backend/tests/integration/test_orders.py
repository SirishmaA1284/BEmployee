from httpx import AsyncClient


async def _setup_customer_and_stocked_product(
    client: AsyncClient, headers: dict, quantity: int = 10, unit_price: str = "250.00"
) -> tuple[dict, dict]:
    customer_resp = await client.post("/api/customers", json={"name": "Rahul"}, headers=headers)
    customer = customer_resp.json()

    product_resp = await client.post(
        "/api/products",
        json={"sku": "COFFEE-500", "name": "Coffee 500g", "unit_price": unit_price},
        headers=headers,
    )
    product = product_resp.json()

    await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": quantity}, headers=headers
    )
    return customer, product


async def test_create_order_decrements_stock_and_generates_invoice(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    customer, product = await _setup_customer_and_stocked_product(client, headers, quantity=10)

    response = await client.post(
        "/api/orders",
        json={"customer_id": customer["id"], "items": [{"product_id": product["id"], "quantity": 3}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "CONFIRMED"
    assert order["subtotal"] == "750.00"
    assert order["total"] == "750.00"
    assert order["invoice_number"] == "INV-000001"

    inv_response = await client.get(f"/api/inventory/{product['id']}", headers=headers)
    assert inv_response.json()["quantity_on_hand"] == 7

    invoice_response = await client.get(f"/api/invoices/{order['invoice_id']}", headers=headers)
    invoice = invoice_response.json()
    assert invoice["status"] == "ISSUED"
    assert invoice["total"] == "750.00"
    assert invoice["amount_due"] == "750.00"


async def test_duplicate_product_lines_are_merged(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    customer, product = await _setup_customer_and_stocked_product(client, headers, quantity=10)

    response = await client.post(
        "/api/orders",
        json={
            "customer_id": customer["id"],
            "items": [
                {"product_id": product["id"], "quantity": 2},
                {"product_id": product["id"], "quantity": 1},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201
    order = response.json()
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 3


async def test_insufficient_stock_rejected_and_no_order_created(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    customer, product = await _setup_customer_and_stocked_product(client, headers, quantity=2)

    response = await client.post(
        "/api/orders",
        json={"customer_id": customer["id"], "items": [{"product_id": product["id"], "quantity": 5}]},
        headers=headers,
    )
    assert response.status_code == 422

    list_response = await client.get("/api/orders", headers=headers)
    assert list_response.json() == []

    inv_response = await client.get(f"/api/inventory/{product['id']}", headers=headers)
    assert inv_response.json()["quantity_on_hand"] == 2  # untouched


async def test_unknown_customer_returns_404(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    _, product = await _setup_customer_and_stocked_product(client, headers)
    import uuid

    response = await client.post(
        "/api/orders",
        json={"customer_id": str(uuid.uuid4()), "items": [{"product_id": product["id"], "quantity": 1}]},
        headers=headers,
    )
    assert response.status_code == 404


async def test_employee_can_create_order(client: AsyncClient, business: dict, employee_headers: dict):
    customer, product = await _setup_customer_and_stocked_product(client, business["owner_headers"])

    response = await client.post(
        "/api/orders",
        json={"customer_id": customer["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
        headers=employee_headers,
    )
    assert response.status_code == 201


async def test_employee_cannot_cancel_order(client: AsyncClient, business: dict, employee_headers: dict):
    customer, product = await _setup_customer_and_stocked_product(client, business["owner_headers"])
    order_resp = await client.post(
        "/api/orders",
        json={"customer_id": customer["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
        headers=business["owner_headers"],
    )
    order_id = order_resp.json()["id"]

    response = await client.post(f"/api/orders/{order_id}/cancel", headers=employee_headers)
    assert response.status_code == 403


async def test_cancel_order_restores_stock_and_voids_invoice(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    customer, product = await _setup_customer_and_stocked_product(client, headers, quantity=10)

    order_resp = await client.post(
        "/api/orders",
        json={"customer_id": customer["id"], "items": [{"product_id": product["id"], "quantity": 4}]},
        headers=headers,
    )
    order = order_resp.json()

    cancel_response = await client.post(f"/api/orders/{order['id']}/cancel", headers=headers)
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"

    inv_response = await client.get(f"/api/inventory/{product['id']}", headers=headers)
    assert inv_response.json()["quantity_on_hand"] == 10  # restored

    invoice_response = await client.get(f"/api/invoices/{order['invoice_id']}", headers=headers)
    assert invoice_response.json()["status"] == "VOID"

    second_cancel = await client.post(f"/api/orders/{order['id']}/cancel", headers=headers)
    assert second_cancel.status_code == 409
