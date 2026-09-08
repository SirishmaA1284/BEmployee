from httpx import AsyncClient


async def test_list_policies_empty(client: AsyncClient, business: dict):
    response = await client.get("/api/policies", headers=business["owner_headers"])
    assert response.status_code == 200
    assert response.json() == []


async def test_owner_can_upsert_and_read_policy(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    response = await client.put(
        "/api/policies/po_threshold",
        json={
            "policy_type": "MONEY_THRESHOLD",
            "key": "po_threshold",
            "value": {"amount": "5000.00"},
            "description": "POs above this need approval",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["key"] == "po_threshold"
    assert body["value"] == {"amount": "5000.00"}

    listed = await client.get("/api/policies", headers=headers)
    assert len(listed.json()) == 1


async def test_upsert_same_key_updates(client: AsyncClient, business: dict):
    headers = business["owner_headers"]
    payload = {
        "policy_type": "MONEY_THRESHOLD",
        "key": "order_threshold",
        "value": {"amount": "1000.00"},
    }
    await client.put("/api/policies/order_threshold", json=payload, headers=headers)
    response = await client.put(
        "/api/policies/order_threshold",
        json={**payload, "value": {"amount": "2000.00"}},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["value"] == {"amount": "2000.00"}
    listed = await client.get("/api/policies", headers=headers)
    assert len(listed.json()) == 1


async def test_employee_cannot_write_policy(client: AsyncClient, business: dict, employee_headers: dict):
    response = await client.put(
        "/api/policies/po_threshold",
        json={"policy_type": "MONEY_THRESHOLD", "key": "po_threshold", "value": {"amount": "1"}},
        headers=employee_headers,
    )
    assert response.status_code == 403


async def test_employee_can_read_policies(client: AsyncClient, business: dict, employee_headers: dict):
    await client.put(
        "/api/policies/po_threshold",
        json={"policy_type": "MONEY_THRESHOLD", "key": "po_threshold", "value": {"amount": "5000"}},
        headers=business["owner_headers"],
    )
    response = await client.get("/api/policies", headers=employee_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
