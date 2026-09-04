"""Covers docs/threat-model.md T4 (cross-tenant data access) and T5
(privilege escalation) at the API layer.
"""

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str, full_name: str) -> str:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "a-strong-password", "full_name": full_name},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


async def _create_business(client: AsyncClient, token: str, name: str) -> str:
    response = await client.post(
        "/api/businesses", json={"name": name}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_user_cannot_list_members_of_a_business_they_do_not_belong_to(client: AsyncClient):
    owner_a_token = await _register_and_login(client, "owner-a@example.com", "Owner A")
    business_a_id = await _create_business(client, owner_a_token, "Business A")

    owner_b_token = await _register_and_login(client, "owner-b@example.com", "Owner B")

    # Owner B knows Business A's id (e.g. guessed/leaked) but is not a member.
    response = await client.get(
        "/api/businesses/members",
        headers={"Authorization": f"Bearer {owner_b_token}", "X-Business-Id": business_a_id},
    )
    assert response.status_code == 403


async def test_user_cannot_invite_members_into_a_business_they_do_not_belong_to(
    client: AsyncClient,
):
    owner_a_token = await _register_and_login(client, "owner-a@example.com", "Owner A")
    business_a_id = await _create_business(client, owner_a_token, "Business A")

    owner_b_token = await _register_and_login(client, "owner-b@example.com", "Owner B")

    response = await client.post(
        "/api/businesses/members",
        json={"email": "owner-b@example.com", "role": "OWNER"},
        headers={"Authorization": f"Bearer {owner_b_token}", "X-Business-Id": business_a_id},
    )
    assert response.status_code == 403


async def test_employee_cannot_invite_new_members(client: AsyncClient):
    owner_token = await _register_and_login(client, "owner@example.com", "Owner")
    business_id = await _create_business(client, owner_token, "Store")

    employee_token = await _register_and_login(client, "employee@example.com", "Employee")
    await client.post(
        "/api/businesses/members",
        json={"email": "employee@example.com", "role": "EMPLOYEE"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Business-Id": business_id},
    )

    # Employee tries to invite someone else — only OWNER may do this.
    escalation_attempt = await client.post(
        "/api/businesses/members",
        json={"email": "owner@example.com", "role": "ADMIN"},
        headers={"Authorization": f"Bearer {employee_token}", "X-Business-Id": business_id},
    )
    assert escalation_attempt.status_code == 403


async def test_missing_business_header_is_rejected(client: AsyncClient):
    owner_token = await _register_and_login(client, "owner@example.com", "Owner")
    await _create_business(client, owner_token, "Store")

    response = await client.get(
        "/api/businesses/members", headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert response.status_code == 400


async def test_malformed_business_id_is_rejected(client: AsyncClient):
    owner_token = await _register_and_login(client, "owner@example.com", "Owner")

    response = await client.get(
        "/api/businesses/members",
        headers={"Authorization": f"Bearer {owner_token}", "X-Business-Id": "not-a-uuid"},
    )
    assert response.status_code == 400


async def test_unauthenticated_requests_are_rejected(client: AsyncClient):
    response = await client.get("/api/businesses")
    assert response.status_code == 401

    response = await client.post("/api/businesses", json={"name": "Nope"})
    assert response.status_code == 401
