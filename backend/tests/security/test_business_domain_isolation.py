"""Cross-tenant isolation for Phase 3 domains (products/orders/purchase
orders as representative samples of each access pattern: soft-deleted
resource, transactional child resource, admin-only resource). See
docs/threat-model.md T4 — a resource id from Business A must be invisible
through Business B's membership context, not just blocked at the business
level (already covered for auth/business endpoints in
tests/security/test_multi_tenancy.py).
"""

from httpx import AsyncClient


async def _register_and_own_business(client: AsyncClient, email: str, biz_name: str) -> dict:
    register = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "a-strong-password", "full_name": "Owner"},
    )
    token = register.json()["access_token"]
    create = await client.post(
        "/api/businesses", json={"name": biz_name}, headers={"Authorization": f"Bearer {token}"}
    )
    business_id = create.json()["id"]
    return {"headers": {"Authorization": f"Bearer {token}", "X-Business-Id": business_id}}


async def test_product_from_business_a_invisible_to_business_b(client: AsyncClient, business: dict):
    owner_a_headers = business["owner_headers"]
    product_resp = await client.post(
        "/api/products",
        json={"sku": "COFFEE", "name": "Coffee", "unit_price": "10.00"},
        headers=owner_a_headers,
    )
    product_id = product_resp.json()["id"]

    biz_b = await _register_and_own_business(client, "owner-b@example.com", "Business B")

    response = await client.get(f"/api/products/{product_id}", headers=biz_b["headers"])
    assert response.status_code == 404


async def test_order_from_business_a_invisible_to_business_b(client: AsyncClient, business: dict):
    owner_a_headers = business["owner_headers"]
    customer_resp = await client.post("/api/customers", json={"name": "Rahul"}, headers=owner_a_headers)
    product_resp = await client.post(
        "/api/products",
        json={"sku": "COFFEE", "name": "Coffee", "unit_price": "10.00"},
        headers=owner_a_headers,
    )
    product = product_resp.json()
    await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": 10}, headers=owner_a_headers
    )
    order_resp = await client.post(
        "/api/orders",
        json={
            "customer_id": customer_resp.json()["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers=owner_a_headers,
    )
    order_id = order_resp.json()["id"]

    biz_b = await _register_and_own_business(client, "owner-b@example.com", "Business B")

    get_response = await client.get(f"/api/orders/{order_id}", headers=biz_b["headers"])
    assert get_response.status_code == 404

    cancel_response = await client.post(f"/api/orders/{order_id}/cancel", headers=biz_b["headers"])
    assert cancel_response.status_code == 404


async def test_purchase_order_from_business_a_invisible_to_business_b(
    client: AsyncClient, business: dict
):
    owner_a_headers = business["owner_headers"]
    product_resp = await client.post(
        "/api/products",
        json={"sku": "COFFEE", "name": "Coffee", "unit_price": "10.00"},
        headers=owner_a_headers,
    )
    supplier_resp = await client.post("/api/suppliers", json={"name": "Supplier A"}, headers=owner_a_headers)
    po_resp = await client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": supplier_resp.json()["id"],
            "items": [{"product_id": product_resp.json()["id"], "quantity": 1, "unit_cost": "1.00"}],
        },
        headers=owner_a_headers,
    )
    po_id = po_resp.json()["id"]

    biz_b = await _register_and_own_business(client, "owner-b@example.com", "Business B")

    get_response = await client.get(f"/api/purchase-orders/{po_id}", headers=biz_b["headers"])
    assert get_response.status_code == 404

    send_response = await client.post(f"/api/purchase-orders/{po_id}/send", headers=biz_b["headers"])
    assert send_response.status_code == 404
