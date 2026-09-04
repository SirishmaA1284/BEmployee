from httpx import AsyncClient


async def test_employee_can_create_customer(client: AsyncClient, business: dict, employee_headers: dict):
    response = await client.post(
        "/api/customers", json={"name": "Rahul"}, headers=employee_headers
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Rahul"


async def test_search_customers_by_name(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    await client.post("/api/customers", json={"name": "Rahul Sharma"}, headers=headers)
    await client.post("/api/customers", json={"name": "Priya Singh"}, headers=headers)

    response = await client.get("/api/customers?search=rahul", headers=headers)
    names = [c["name"] for c in response.json()]
    assert names == ["Rahul Sharma"]


async def test_soft_delete_customer(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    create = await client.post("/api/customers", json={"name": "Temp"}, headers=headers)
    customer_id = create.json()["id"]

    delete_response = await client.delete(f"/api/customers/{customer_id}", headers=headers)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/customers/{customer_id}", headers=headers)
    assert get_response.status_code == 404
