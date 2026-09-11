"""Notification read-state integration tests (Phase 9).

Per-user read markers: a notification is unread until the *current member*
marks it read — other members keep their own state. Covers the list
`read` flag, the unread-only filter, single + bulk mark-read endpoints, and
tenant isolation (a notification can only be marked read by its business).
"""

import uuid

from app.models.enums import NotificationSeverity, NotificationType
from app.services.notification_service import notify


async def _create_notification(client, business, db_session, title="Low stock: Coffee"):
    notification = await notify(
        db_session,
        business_id=business["business_id"],
        notification_type=NotificationType.LOW_STOCK,
        severity=NotificationSeverity.WARNING,
        title=title,
        message="Coffee (COF-500) is at 3 units, below its threshold.",
    )
    await db_session.commit()
    return str(notification.id)


async def test_notifications_start_unread_and_mark_read(client, business, db_session):
    headers = business["owner_headers"]
    notification_id = await _create_notification(client, business, db_session)

    listed = (await client.get("/api/notifications", headers=headers)).json()
    assert len(listed) == 1
    assert listed[0]["id"] == notification_id
    assert listed[0]["read"] is False

    # Unread-only filter shows it while unread.
    unread = (await client.get("/api/notifications?unread_only=true", headers=headers)).json()
    assert [n["id"] for n in unread] == [notification_id]

    mark = await client.post(f"/api/notifications/{notification_id}/read", headers=headers)
    assert mark.status_code == 204

    listed = (await client.get("/api/notifications", headers=headers)).json()
    assert listed[0]["read"] is True
    unread = (await client.get("/api/notifications?unread_only=true", headers=headers)).json()
    assert unread == []

    # Marking again is idempotent.
    again = await client.post(f"/api/notifications/{notification_id}/read", headers=headers)
    assert again.status_code == 204


async def test_read_state_is_per_user(client, business, employee_headers, db_session):
    notification_id = await _create_notification(client, business, db_session)

    await client.post(f"/api/notifications/{notification_id}/read", headers=business["owner_headers"])

    owner_view = (await client.get("/api/notifications", headers=business["owner_headers"])).json()
    employee_view = (await client.get("/api/notifications", headers=employee_headers)).json()
    assert owner_view[0]["read"] is True
    assert employee_view[0]["read"] is False


async def test_read_all_marks_every_notification(client, business, employee_headers, db_session):
    await _create_notification(client, business, db_session, title="A")
    await _create_notification(client, business, db_session, title="B")

    mark_all = await client.post("/api/notifications/read-all", headers=employee_headers)
    assert mark_all.status_code == 204

    employee_view = (await client.get("/api/notifications", headers=employee_headers)).json()
    assert all(n["read"] for n in employee_view)
    # The owner is untouched by the employee's read-all.
    owner_view = (await client.get("/api/notifications", headers=business["owner_headers"])).json()
    assert all(not n["read"] for n in owner_view)


async def test_mark_read_is_business_scoped(client, business, db_session):
    notification_id = await _create_notification(client, business, db_session)

    reg2 = await client.post(
        "/api/auth/register",
        json={"email": "other-biz@example.com", "password": "a-strong-password", "full_name": "OB"},
    )
    token2 = reg2.json()["access_token"]
    biz2 = (
        await client.post("/api/businesses", json={"name": "Biz 2"}, headers={"Authorization": f"Bearer {token2}"})
    ).json()
    headers2 = {"Authorization": f"Bearer {token2}", "X-Business-Id": biz2["id"]}

    resp = await client.post(f"/api/notifications/{notification_id}/read", headers=headers2)
    assert resp.status_code == 404


async def test_mark_read_missing_notification_404(client, business):
    resp = await client.post(
        f"/api/notifications/{uuid.uuid4()}/read", headers=business["owner_headers"]
    )
    assert resp.status_code == 404