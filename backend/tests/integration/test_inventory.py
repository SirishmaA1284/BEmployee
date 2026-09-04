from httpx import AsyncClient


async def _create_product(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {"sku": "COFFEE-500", "name": "Coffee 500g", "unit_price": "250.00", "reorder_threshold": 5}
    payload.update(overrides)
    response = await client.post("/api/products", json=payload, headers=headers)
    return response.json()


async def test_adjust_inventory_increases_stock(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)

    response = await client.post(
        f"/api/inventory/{product['id']}/adjust",
        json={"change_quantity": 50, "note": "initial stock take"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["quantity_on_hand"] == 50
    assert body["is_low_stock"] is False


async def test_adjust_inventory_rejects_negative_result(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)

    response = await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": -1}, headers=headers
    )
    assert response.status_code == 422


async def test_adjust_inventory_rejects_zero_change(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)

    response = await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": 0}, headers=headers
    )
    assert response.status_code == 422


async def test_low_stock_only_filter(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    low = await _create_product(client, headers, sku="LOW", name="Low stock item", reorder_threshold=10)
    healthy = await _create_product(
        client, headers, sku="HEALTHY", name="Healthy stock item", reorder_threshold=10
    )
    await client.post(f"/api/inventory/{healthy['id']}/adjust", json={"change_quantity": 100}, headers=headers)
    # `low` stays at 0, below its threshold of 10.

    response = await client.get("/api/inventory?low_stock_only=true", headers=headers)
    names = [row["product_name"] for row in response.json()]
    assert names == ["Low stock item"]


async def test_employee_cannot_adjust_inventory(client: AsyncClient, business: dict, employee_headers: dict):
    product = await _create_product(client, business["owner_headers"])
    response = await client.post(
        f"/api/inventory/{product['id']}/adjust", json={"change_quantity": 10}, headers=employee_headers
    )
    assert response.status_code == 403
