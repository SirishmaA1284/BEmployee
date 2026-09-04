import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, email="owner@example.com", password="a-strong-password"):
    return await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Test Owner"},
    )


async def test_register_creates_user_and_returns_token(client: AsyncClient):
    response = await _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == "owner@example.com"
    assert body["businesses"] == []


async def test_register_rejects_duplicate_email(client: AsyncClient):
    first = await _register(client)
    assert first.status_code == 201

    second = await _register(client)
    assert second.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient):
    response = await client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "short", "full_name": "Short Pass"},
    )
    assert response.status_code == 422


async def test_login_succeeds_with_correct_credentials(client: AsyncClient):
    await _register(client)
    response = await client.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": "a-strong-password"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_fails_with_wrong_password(client: AsyncClient):
    await _register(client)
    response = await client.post(
        "/api/auth/login", json={"email": "owner@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_login_fails_for_unknown_email(client: AsyncClient):
    response = await client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever-password"}
    )
    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_me_returns_current_user(client: AsyncClient):
    register_response = await _register(client)
    token = register_response.json()["access_token"]

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "owner@example.com"


async def test_me_rejects_tampered_token(client: AsyncClient):
    await _register(client)
    response = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
