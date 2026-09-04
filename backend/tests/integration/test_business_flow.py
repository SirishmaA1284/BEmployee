from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str, full_name: str) -> str:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "a-strong-password", "full_name": full_name},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


async def test_create_business_makes_creator_owner(client: AsyncClient):
    token = await _register_and_login(client, "owner@example.com", "Owner")

    response = await client.post(
        "/api/businesses",
        json={"name": "Rahul General Store", "currency": "INR"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Rahul General Store"
    assert body["role"] == "OWNER"


async def test_list_my_businesses_returns_only_my_memberships(client: AsyncClient):
    token_a = await _register_and_login(client, "a@example.com", "Owner A")
    token_b = await _register_and_login(client, "b@example.com", "Owner B")

    await client.post(
        "/api/businesses",
        json={"name": "Business A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    await client.post(
        "/api/businesses",
        json={"name": "Business B"},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    response = await client.get(
        "/api/businesses", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert response.status_code == 200
    names = [b["name"] for b in response.json()]
    assert names == ["Business A"]


async def test_owner_can_invite_existing_user_as_employee(client: AsyncClient):
    owner_token = await _register_and_login(client, "owner@example.com", "Owner")
    await _register_and_login(client, "employee@example.com", "Employee")

    create_response = await client.post(
        "/api/businesses",
        json={"name": "Store"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    business_id = create_response.json()["id"]

    invite_response = await client.post(
        "/api/businesses/members",
        json={"email": "employee@example.com", "role": "EMPLOYEE"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Business-Id": business_id},
    )
    assert invite_response.status_code == 201
    assert invite_response.json()["role"] == "EMPLOYEE"

    members_response = await client.get(
        "/api/businesses/members",
        headers={"Authorization": f"Bearer {owner_token}", "X-Business-Id": business_id},
    )
    emails = {m["email"] for m in members_response.json()}
    assert emails == {"owner@example.com", "employee@example.com"}


async def test_invite_unknown_email_returns_404(client: AsyncClient):
    owner_token = await _register_and_login(client, "owner@example.com", "Owner")
    create_response = await client.post(
        "/api/businesses",
        json={"name": "Store"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    business_id = create_response.json()["id"]

    response = await client.post(
        "/api/businesses/members",
        json={"email": "ghost@example.com", "role": "EMPLOYEE"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Business-Id": business_id},
    )
    assert response.status_code == 404
