from httpx import AsyncClient


async def _create_product(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {
        "sku": "COFFEE-500",
        "name": "Coffee 500g",
        "unit": "packet",
        "unit_price": "250.00",
        "reorder_threshold": 5,
        "reorder_quantity": 20,
    }
    payload.update(overrides)
    response = await client.post("/api/products", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_product_also_creates_zero_inventory(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)

    inv_response = await client.get(f"/api/inventory/{product['id']}", headers=headers)
    assert inv_response.status_code == 200
    body = inv_response.json()
    assert body["quantity_on_hand"] == 0
    assert body["reorder_threshold"] == 5
    assert body["is_low_stock"] is True  # 0 <= 5


async def test_duplicate_sku_rejected(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    await _create_product(client, headers)
    response = await client.post(
        "/api/products",
        json={"sku": "COFFEE-500", "name": "Coffee again", "unit_price": "1.00"},
        headers=headers,
    )
    assert response.status_code == 409


async def test_list_products_search(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    await _create_product(client, headers, sku="COFFEE-500", name="Coffee 500g")
    await _create_product(client, headers, sku="SUGAR-1KG", name="Sugar 1kg")

    response = await client.get("/api/products?search=coffee", headers=headers)
    names = [p["name"] for p in response.json()]
    assert names == ["Coffee 500g"]


async def test_soft_deleted_product_excluded_from_list_and_get(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)

    delete_response = await client.delete(f"/api/products/{product['id']}", headers=headers)
    assert delete_response.status_code == 204

    list_response = await client.get("/api/products", headers=headers)
    assert list_response.json() == []

    get_response = await client.get(f"/api/products/{product['id']}", headers=headers)
    assert get_response.status_code == 404


async def test_update_product_price(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)

    response = await client.patch(
        f"/api/products/{product['id']}", json={"unit_price": "299.00"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["unit_price"] == "299.00"


async def test_employee_cannot_create_product(client: AsyncClient, business: dict, employee_headers: dict):
    response = await client.post(
        "/api/products",
        json={"sku": "X", "name": "X", "unit_price": "1.00"},
        headers=employee_headers,
    )
    assert response.status_code == 403


async def test_employee_can_read_products(client: AsyncClient, business: dict, employee_headers: dict):
    await _create_product(client, business["owner_headers"])
    response = await client.get("/api/products", headers=employee_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
