from httpx import AsyncClient


async def _create_product(client: AsyncClient, headers: dict) -> dict:
    response = await client.post(
        "/api/products",
        json={"sku": "COFFEE-500", "name": "Coffee 500g", "unit_price": "250.00"},
        headers=headers,
    )
    return response.json()


async def _create_supplier(client: AsyncClient, headers: dict, name: str, is_active: bool = True) -> dict:
    response = await client.post("/api/suppliers", json={"name": name}, headers=headers)
    supplier = response.json()
    if not is_active:
        await client.patch(
            f"/api/suppliers/{supplier['id']}", json={"is_active": False}, headers=headers
        )
    return supplier


async def test_compare_supplier_prices_ranks_active_and_cheapest_first(
    client: AsyncClient, business: dict
):
    headers = business["owner_headers"]
    product = await _create_product(client, headers)

    supplier_a = await _create_supplier(client, headers, "Supplier A")
    supplier_b = await _create_supplier(client, headers, "Supplier B")
    supplier_c = await _create_supplier(client, headers, "Cheap Inactive", is_active=False)

    await client.post(
        f"/api/suppliers/{supplier_a['id']}/products",
        json={"product_id": product["id"], "price": "20.00", "lead_time_days": 3},
        headers=headers,
    )
    await client.post(
        f"/api/suppliers/{supplier_b['id']}/products",
        json={"product_id": product["id"], "price": "15.00", "lead_time_days": 5},
        headers=headers,
    )
    await client.post(
        f"/api/suppliers/{supplier_c['id']}/products",
        json={"product_id": product["id"], "price": "1.00", "lead_time_days": 1},
        headers=headers,
    )

    response = await client.get(
        f"/api/suppliers/compare?product_id={product['id']}", headers=headers
    )
    assert response.status_code == 200
    names = [row["supplier_name"] for row in response.json()]
    # Active suppliers first (cheapest of those first), inactive last even
    # though it has the lowest price.
    assert names == ["Supplier B", "Supplier A", "Cheap Inactive"]


async def test_cannot_link_product_from_another_business(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    supplier = await _create_supplier(client, headers, "Supplier A")

    import uuid

    response = await client.post(
        f"/api/suppliers/{supplier['id']}/products",
        json={"product_id": str(uuid.uuid4()), "price": "10.00", "lead_time_days": 1},
        headers=headers,
    )
    assert response.status_code == 404


async def test_employee_cannot_create_supplier(client: AsyncClient, business: dict, employee_headers: dict):
    response = await client.post("/api/suppliers", json={"name": "X"}, headers=employee_headers)
    assert response.status_code == 403
