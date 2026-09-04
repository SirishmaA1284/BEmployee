from httpx import AsyncClient


async def _create_product(client: AsyncClient, headers: dict) -> dict:
    response = await client.post(
        "/api/products",
        json={"sku": "COFFEE-500", "name": "Coffee 500g", "unit_price": "250.00"},
        headers=headers,
    )
    return response.json()


async def _create_supplier(client: AsyncClient, headers: dict) -> dict:
    response = await client.post("/api/suppliers", json={"name": "Supplier A"}, headers=headers)
    return response.json()


async def test_create_po_with_explicit_unit_cost(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)
    supplier = await _create_supplier(client, headers)

    response = await client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "items": [{"product_id": product["id"], "quantity": 10, "unit_cost": "15.00"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["total"] == "150.00"


async def test_create_po_falls_back_to_supplier_product_price(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)
    supplier = await _create_supplier(client, headers)
    await client.post(
        f"/api/suppliers/{supplier['id']}/products",
        json={"product_id": product["id"], "price": "12.50", "lead_time_days": 4},
        headers=headers,
    )

    response = await client.post(
        "/api/purchase-orders",
        json={"supplier_id": supplier["id"], "items": [{"product_id": product["id"], "quantity": 4}]},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["total"] == "50.00"


async def test_create_po_without_price_and_no_supplier_product_fails(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)
    supplier = await _create_supplier(client, headers)

    response = await client.post(
        "/api/purchase-orders",
        json={"supplier_id": supplier["id"], "items": [{"product_id": product["id"], "quantity": 4}]},
        headers=headers,
    )
    assert response.status_code == 422


async def test_cannot_create_po_against_inactive_supplier(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)
    supplier = await _create_supplier(client, headers)
    await client.patch(f"/api/suppliers/{supplier['id']}", json={"is_active": False}, headers=headers)

    response = await client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "items": [{"product_id": product["id"], "quantity": 1, "unit_cost": "1.00"}],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_send_then_receive_increments_inventory(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)
    supplier = await _create_supplier(client, headers)

    create_resp = await client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "items": [{"product_id": product["id"], "quantity": 20, "unit_cost": "10.00"}],
        },
        headers=headers,
    )
    po_id = create_resp.json()["id"]

    receive_before_send = await client.post(f"/api/purchase-orders/{po_id}/receive", headers=headers)
    assert receive_before_send.status_code == 409

    send_resp = await client.post(f"/api/purchase-orders/{po_id}/send", headers=headers)
    assert send_resp.status_code == 200
    assert send_resp.json()["status"] == "SENT"

    send_again = await client.post(f"/api/purchase-orders/{po_id}/send", headers=headers)
    assert send_again.status_code == 409

    receive_resp = await client.post(f"/api/purchase-orders/{po_id}/receive", headers=headers)
    assert receive_resp.status_code == 200
    assert receive_resp.json()["status"] == "COMPLETED"

    inv_response = await client.get(f"/api/inventory/{product['id']}", headers=headers)
    assert inv_response.json()["quantity_on_hand"] == 20


async def test_cancel_draft_po(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)
    supplier = await _create_supplier(client, headers)

    create_resp = await client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "items": [{"product_id": product["id"], "quantity": 5, "unit_cost": "1.00"}],
        },
        headers=headers,
    )
    po_id = create_resp.json()["id"]

    cancel_resp = await client.post(f"/api/purchase-orders/{po_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    cancel_again = await client.post(f"/api/purchase-orders/{po_id}/cancel", headers=headers)
    assert cancel_again.status_code == 409


async def test_employee_cannot_create_purchase_order(
    client: AsyncClient, business: dict, employee_headers: dict
):
    product = await _create_product(client, business["owner_headers"])
    supplier = await _create_supplier(client, business["owner_headers"])

    response = await client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "items": [{"product_id": product["id"], "quantity": 1, "unit_cost": "1.00"}],
        },
        headers=employee_headers,
    )
    assert response.status_code == 403
