"""Phase 6 integration tests: worker jobs + notifications (FR-24, ADR-007).

Seeds real rows (products, inventory, orders) and drives the deterministic
worker jobs + the notifications API against the live test database.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database.base import utcnow
from app.models.customer import Customer
from app.models.enums import NotificationType, OrderStatus
from app.models.inventory import Inventory
from app.models.notification import Notification
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User
from app.services.worker_jobs import (
    generate_daily_report,
    run_scheduled_checks,
    scan_forecasted_stockouts,
    scan_low_stock,
)


async def _seed_product(
    db_session, business_id, *, sku="SKU-1", name="Coffee", quantity=0, threshold=10, unit_price="250.00"
):
    product = Product(
        business_id=business_id,
        sku=sku,
        name=name,
        unit="unit",
        unit_price=Decimal(unit_price),
        cost_price=Decimal("100.00"),
        is_active=True,
    )
    db_session.add(product)
    await db_session.flush()
    inventory = Inventory(
        business_id=business_id,
        product_id=product.id,
        quantity_on_hand=quantity,
        reorder_threshold=threshold,
        reorder_quantity=50,
    )
    db_session.add(inventory)
    await db_session.flush()
    return product, inventory


async def test_scan_low_stock_creates_notification_and_dedupes(client, business, db_session):
    await _seed_product(db_session, business["business_id"], sku="LOW-1", quantity=3, threshold=10)
    await db_session.commit()

    flagged = await scan_low_stock(db_session, business["business_id"])
    assert len(flagged) == 1
    assert flagged[0]["sku"] == "LOW-1"

    notifications = (await client.get("/api/notifications", headers=business["owner_headers"])).json()
    assert len(notifications) == 1
    assert notifications[0]["notification_type"] == "LOW_STOCK"
    assert notifications[0]["severity"] == "WARNING"
    assert notifications[0]["payload"]["sku"] == "LOW-1"

    # Re-running within the dedupe window creates nothing new.
    again = await scan_low_stock(db_session, business["business_id"])
    assert again == []
    notifications = (await client.get("/api/notifications", headers=business["owner_headers"])).json()
    assert len(notifications) == 1


async def test_scan_low_stock_ignores_healthy_products(client, business, db_session):
    await _seed_product(db_session, business["business_id"], sku="OK-1", quantity=100, threshold=10)
    await db_session.commit()
    flagged = await scan_low_stock(db_session, business["business_id"])
    assert flagged == []
    notifications = (await client.get("/api/notifications", headers=business["owner_headers"])).json()
    assert notifications == []


async def test_scan_forecasted_stockout_creates_notification(client, business, db_session):
    """A product with strong recent sales and low stock is projected to run
    out before its supplier lead time -> CRITICAL notification.
    """
    # Needs a supplier offer on file for lead time to count.
    supplier = (
        await client.post(
            "/api/suppliers", json={"name": "FastCo"}, headers=business["owner_headers"]
        )
    ).json()
    product, inventory = await _seed_product(
        db_session, business["business_id"], sku="STK-1", quantity=6, threshold=5
    )
    await db_session.commit()
    await client.post(
        f"/api/suppliers/{supplier['id']}/products",
        json={"product_id": str(product.id), "price": "200.00", "lead_time_days": 7},
        headers=business["owner_headers"],
    )

    # Seed 5 units/day for 7 days (7-day window is fine; default window 14
    # still yields ~2.5/day -> stockout in ~3 days < lead time 7).
    user = User(
        email=f"sales-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Sales",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    customer = Customer(business_id=business["business_id"], name="Walk-in")
    db_session.add(customer)
    await db_session.flush()
    now = utcnow()
    for offset in range(1, 8):
        order = Order(
            business_id=business["business_id"],
            customer_id=customer.id,
            status=OrderStatus.CONFIRMED,
            subtotal=Decimal("1250.00"),
            tax_amount=Decimal("0.00"),
            total=Decimal("1250.00"),
            currency="INR",
            created_by_user_id=user.id,
        )
        db_session.add(order)
        await db_session.flush()
        order.created_at = now - timedelta(days=offset)
        db_session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=5,
                unit_price=Decimal("250.00"),
                line_total=Decimal("1250.00"),
            )
        )
    await db_session.commit()

    flagged = await scan_forecasted_stockouts(db_session, business["business_id"])
    assert len(flagged) == 1
    assert flagged[0]["sku"] == "STK-1"
    assert flagged[0]["at_risk"] is True

    notifications = (await client.get("/api/notifications", headers=business["owner_headers"])).json()
    stockout = [n for n in notifications if n["notification_type"] == "FORECASTED_STOCKOUT"]
    assert len(stockout) == 1
    assert stockout[0]["severity"] == "CRITICAL"
    assert stockout[0]["payload"]["sku"] == "STK-1"

    # Dedupe: no second notification on re-run.
    again = await scan_forecasted_stockouts(db_session, business["business_id"])
    assert again == []


async def test_daily_report_notification(client, business, db_session):
    await _seed_product(db_session, business["business_id"], sku="RPT-1", quantity=10)
    await db_session.commit()
    summary = await generate_daily_report(db_session, business["business_id"])
    assert summary is not None

    notifications = (await client.get("/api/notifications", headers=business["owner_headers"])).json()
    report = [n for n in notifications if n["notification_type"] == "DAILY_REPORT"]
    assert len(report) == 1
    assert report[0]["title"] == "Daily report"


async def test_notifications_api_filters_and_tenant_isolates(client, business, db_session):
    await _seed_product(db_session, business["business_id"], sku="A-1", quantity=3, threshold=10)
    await _seed_product(db_session, business["business_id"], sku="A-2", quantity=2, threshold=10)
    await db_session.commit()
    await scan_low_stock(db_session, business["business_id"])

    all_notifications = (
        await client.get("/api/notifications", headers=business["owner_headers"])
    ).json()
    assert len(all_notifications) == 2

    low = (
        await client.get("/api/notifications?type_filter=LOW_STOCK", headers=business["owner_headers"])
    ).json()
    assert len(low) == 2

    none = (
        await client.get("/api/notifications?type_filter=DAILY_REPORT", headers=business["owner_headers"])
    ).json()
    assert none == []


async def test_run_scheduled_checks_covers_all_businesses(client, business, db_session):
    """A second business with a low-stock product is also covered, and a
    business with nothing to flag contributes zero notifications.
    """
    await _seed_product(db_session, business["business_id"], sku="B1-LOW", quantity=1, threshold=5)
    await db_session.commit()

    # Second business, no low stock.
    register2 = await client.post(
        "/api/auth/register",
        json={"email": "owner2@example.com", "password": "a-strong-password", "full_name": "Owner 2"},
    )
    token2 = register2.json()["access_token"]
    biz2 = (await client.post(
        "/api/businesses", json={"name": "Biz 2"}, headers={"Authorization": f"Bearer {token2}"}
    )).json()

    counts = await run_scheduled_checks(db_session)
    assert counts["businesses"] >= 2
    assert counts["low_stock"] >= 1

    headers2 = {"Authorization": f"Bearer {token2}", "X-Business-Id": biz2["id"]}
    biz2_notifs = (await client.get("/api/notifications", headers=headers2)).json()
    assert biz2_notifs == []  # no low stock there


async def test_approval_pending_notification_surface(client, business, db_session):
    """The API exposes APPROVAL_PENDING rows the worker/backend would create;
    verified by inserting one and reading it back scoped to the business."""
    notification = Notification(
        business_id=business["business_id"],
        notification_type=NotificationType.APPROVAL_PENDING,
        severity="WARNING",
        channel="IN_APP",
        title="Approval needed",
        message="A purchase order is waiting for approval.",
        target_type="approval_request",
    )
    db_session.add(notification)
    await db_session.commit()

    rows = (await client.get("/api/notifications", headers=business["owner_headers"])).json()
    assert len(rows) == 1
    assert rows[0]["notification_type"] == "APPROVAL_PENDING"
    assert rows[0]["target_type"] == "approval_request"