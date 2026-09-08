"""Phase 8 hardening tests: refresh-token rotation, logout, rate limiting.

Covers the rotating refresh-token lifecycle (issue -> rotate -> revoke),
that a replayed refresh token is rejected, that the rate limiter returns 429
on auth/agent endpoints, and that reset_rate_limits works for the suite.
"""

from sqlalchemy import select

from app.models.refresh_token import RefreshToken


async def test_login_returns_refresh_token_and_rotation_works(client, business):
    """Login returns a refresh token; refreshing revokes it and issues a new
    one (rotation). The old token is then rejected.
    """
    login = await client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "a-strong-password"},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["refresh_token"]
    first_refresh = body["refresh_token"]

    # Rotate once -> new refresh token, fresh access token.
    r1 = await client.post(
        "/api/auth/refresh", json={"refresh_token": first_refresh}
    )
    assert r1.status_code == 200
    second_refresh = r1.json()["refresh_token"]
    assert second_refresh != first_refresh
    assert r1.json()["access_token"]

    # The rotated-out token is now rejected (replay defense).
    replay = await client.post(
        "/api/auth/refresh", json={"refresh_token": first_refresh}
    )
    assert replay.status_code == 401

    # The new token still works.
    r2 = await client.post(
        "/api/auth/refresh", json={"refresh_token": second_refresh}
    )
    assert r2.status_code == 200


async def test_refresh_rejects_garbage_token(client):
    resp = await client.post(
        "/api/auth/refresh", json={"refresh_token": "definitely-not-a-token"}
    )
    assert resp.status_code == 401


async def test_logout_revokes_refresh_token(client, business):
    login = await client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "a-strong-password"},
    )
    token = login.json()["refresh_token"]

    logout = await client.post("/api/auth/logout", json={"refresh_token": token})
    assert logout.status_code == 204

    # After logout, the refresh token is dead.
    refresh = await client.post("/api/auth/refresh", json={"refresh_token": token})
    assert refresh.status_code == 401

    # Logout is idempotent (already revoked).
    again = await client.post("/api/auth/logout", json={"refresh_token": token})
    assert again.status_code == 204


async def test_register_issues_refresh_token(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "fresh@example.com", "password": "a-strong-password", "full_name": "Fresh"},
    )
    assert resp.status_code == 201
    assert resp.json()["refresh_token"]


async def test_refresh_tokens_are_stored_hashed(client, business, db_session):
    login = await client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "a-strong-password"},
    )
    plaintext = login.json()["refresh_token"]
    rows = (await db_session.execute(select(RefreshToken))).scalars().all()
    # The business fixture's register also issued a token, so >= 1 row. All
    # stored values must be SHA-256 hex (64 chars), never the plaintext token.
    assert len(rows) >= 1
    for row in rows:
        assert row.token_hash != plaintext
        assert len(row.token_hash) == 64


async def test_rate_limit_returns_429_on_register(client):
    """More than 10 registrations from the same IP in a window -> 429."""
    from app.security.rate_limit import reset_rate_limits

    reset_rate_limits()
    for i in range(10):
        resp = await client.post(
            "/api/auth/register",
            json={
                "email": f"rl-{i}@example.com",
                "password": "a-strong-password",
                "full_name": "RL",
            },
        )
        assert resp.status_code == 201, resp.text
    # 11th hits the limit.
    resp = await client.post(
        "/api/auth/register",
        json={"email": "rl-11@example.com", "password": "a-strong-password", "full_name": "RL"},
    )
    assert resp.status_code == 429

    # After reset, a register is allowed again.
    reset_rate_limits()
    resp = await client.post(
        "/api/auth/register",
        json={"email": "rl-12@example.com", "password": "a-strong-password", "full_name": "RL"},
    )
    assert resp.status_code == 201


async def test_refresh_endpoint_has_its_own_rate_limit(client, business):
    from app.security.rate_limit import reset_rate_limits

    reset_rate_limits()
    # 30 refreshes in a window (any token, even garbage, still counts) -> 429.
    for i in range(30):
        await client.post("/api/auth/refresh", json={"refresh_token": "x"})
    resp = await client.post("/api/auth/refresh", json={"refresh_token": "x"})
    assert resp.status_code == 429
    reset_rate_limits()