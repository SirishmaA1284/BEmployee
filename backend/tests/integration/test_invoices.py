from httpx import AsyncClient


async def _create_paid_order_invoice(client: AsyncClient, headers: dict) -> dict:
    customer_resp = await client.post("/api/customers", json={"name": "Rahul"}, headers=headers)
    customer = customer_resp.json()
    product_resp = await client.post(
        "/api/products",
        json={"sku": "COFFEE-500", "name": "Coffee 500g", "unit_price": "100.00"},
        headers=headers,
    )
    product = product_resp.json()
    await client.post(f"/api/inventory/{product['id']}/adjust", json={"change_quantity": 10}, headers=headers)

    order_resp = await client.post(
        "/api/orders",
        json={"customer_id": customer["id"], "items": [{"product_id": product["id"], "quantity": 2}]},
        headers=headers,
    )
    return order_resp.json()


async def test_partial_then_full_payment_marks_invoice_paid(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    order = await _create_paid_order_invoice(client, headers)
    invoice_id = order["invoice_id"]

    partial = await client.post(
        f"/api/invoices/{invoice_id}/payments",
        json={"amount": "100.00", "method": "CASH"},
        headers=headers,
    )
    assert partial.status_code == 201
    body = partial.json()
    assert body["status"] == "ISSUED"
    assert body["amount_paid"] == "100.00"
    assert body["amount_due"] == "100.00"

    full = await client.post(
        f"/api/invoices/{invoice_id}/payments",
        json={"amount": "100.00", "method": "UPI"},
        headers=headers,
    )
    assert full.status_code == 201
    body = full.json()
    assert body["status"] == "PAID"
    assert body["amount_due"] == "0.00"


async def test_overpayment_rejected(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    order = await _create_paid_order_invoice(client, headers)

    response = await client.post(
        f"/api/invoices/{order['invoice_id']}/payments",
        json={"amount": "9999.00", "method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_cannot_pay_void_invoice(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    order = await _create_paid_order_invoice(client, headers)
    await client.post(f"/api/orders/{order['id']}/cancel", headers=headers)

    response = await client.post(
        f"/api/invoices/{order['invoice_id']}/payments",
        json={"amount": "1.00", "method": "CASH"},
        headers=headers,
    )
    assert response.status_code == 409
