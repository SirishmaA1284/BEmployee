"""Scheduled deterministic checks for the worker process (FR-24, ADR-007).

These are the APScheduler jobs' bodies. Each is fully deterministic — it
reads state, computes, and writes notifications; it never calls the LLM.
Any *action* that results from a check (e.g. a low-stock-driven purchase
order) still flows through the same tool registry / policy / approval
pipeline as a user-triggered one — the worker never bypasses it.

Jobs:
- `scan_low_stock`: products at or below reorder threshold.
- `scan_forecasted_stockouts`: products projected to run out before the
  fastest reorder could arrive (FR-13 forecasting).
- `generate_daily_report`: the sales summary as a DAILY_REPORT notification.

Each scan dedupes per (type, target) so a business isn't re-notified about
the same product every run — a product is re-flagged only after `lookback`
passes (or its state meaningfully changes).
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business
from app.models.enums import NotificationSeverity, NotificationType
from app.models.inventory import Inventory
from app.models.notification import Notification
from app.models.product import Product
from app.services.forecasting import forecast_for_business
from app.services.inventory_service import is_low_stock
from app.services.notification_service import notify
from app.services.reporting import sales_summary

logger = logging.getLogger(__name__)

# Re-notify about the same target only after this long (prevents a flood of
# duplicate rows on every worker tick while still re-alerting if it persists).
_DEDUPE_LOOKBACK = timedelta(hours=12)


async def _already_notified(
    db: AsyncSession,
    business_id: uuid.UUID,
    notification_type: NotificationType,
    target_type: str,
    target_id: uuid.UUID,
    *,
    lookback: timedelta = _DEDUPE_LOOKBACK,
) -> bool:
    since = datetime.now(timezone.utc) - lookback
    result = await db.execute(
        select(Notification.id).where(
            Notification.business_id == business_id,
            Notification.notification_type == notification_type,
            Notification.target_type == target_type,
            Notification.target_id == target_id,
            Notification.created_at >= since,
        )
    )
    return result.first() is not None


async def scan_low_stock(db: AsyncSession, business_id: uuid.UUID) -> list[dict]:
    """Flag products at or below their reorder threshold. Returns the rows
    that produced a notification (for logging/tests).
    """
    result = await db.execute(
        select(Product, Inventory)
        .join(Inventory, Inventory.product_id == Product.id)
        .where(Product.business_id == business_id, Product.deleted_at.is_(None))
    )
    flagged: list[dict] = []
    for product, inventory in result.all():
        if not is_low_stock(inventory.quantity_on_hand, inventory.reorder_threshold):
            continue
        if await _already_notified(
            db, business_id, NotificationType.LOW_STOCK, "product", product.id
        ):
            continue
        await notify(
            db,
            business_id=business_id,
            notification_type=NotificationType.LOW_STOCK,
            severity=NotificationSeverity.WARNING,
            title="Low stock",
            message=(
                f"{product.name} ({product.sku}) is at {inventory.quantity_on_hand} "
                f"units, below its reorder threshold of {inventory.reorder_threshold}."
            ),
            payload={
                "product_id": str(product.id),
                "sku": product.sku,
                "quantity_on_hand": inventory.quantity_on_hand,
                "reorder_threshold": inventory.reorder_threshold,
            },
            target_type="product",
            target_id=product.id,
        )
        flagged.append(
            {"product_id": str(product.id), "sku": product.sku, "quantity_on_hand": inventory.quantity_on_hand}
        )
    await db.commit()
    return flagged


async def scan_forecasted_stockouts(db: AsyncSession, business_id: uuid.UUID) -> list[dict]:
    """Flag products projected to run out before the fastest reorder could
    arrive (deterministic forecast, FR-13).
    """
    rows = await forecast_for_business(db, business_id, at_risk_only=True)
    flagged: list[dict] = []
    for row in rows:
        product_id = uuid.UUID(row["product_id"])
        if await _already_notified(
            db, business_id, NotificationType.FORECASTED_STOCKOUT, "product", product_id
        ):
            continue
        await notify(
            db,
            business_id=business_id,
            notification_type=NotificationType.FORECASTED_STOCKOUT,
            severity=NotificationSeverity.CRITICAL,
            title="Forecasted stockout",
            message=(
                f"{row['name']} ({row['sku']}) is projected to run out in "
                f"{row['days_until_stockout']} day(s) ({row['stockout_date']}) at "
                f"a projected demand of {row['projected_daily_demand']}/day — before a "
                f"reorder (best lead time {row['best_lead_time_days']} day(s)) could arrive."
            ),
            payload=row,
            target_type="product",
            target_id=product_id,
        )
        flagged.append(row)
    await db.commit()
    return flagged


async def generate_daily_report(db: AsyncSession, business_id: uuid.UUID) -> dict | None:
    """Publish the sales summary as a DAILY_REPORT notification. Always
    re-sends (a daily report is expected once a day) — no dedupe.
    """
    summary = await sales_summary(db, business_id)
    await notify(
        db,
        business_id=business_id,
        notification_type=NotificationType.DAILY_REPORT,
        severity=NotificationSeverity.INFO,
        title="Daily report",
        message=(
            f"{summary['order_count']} orders, gross sales {summary['gross_sales']}, "
            f"collected {summary['collected']}, outstanding {summary['outstanding']}."
        ),
        payload=summary,
        target_type="report",
    )
    await db.commit()
    return summary


async def run_scheduled_checks(db: AsyncSession) -> dict[str, int]:
    """Run the low-stock and stockout scans for every business (the worker's
    main tick). Returns counts for logging/tests. The daily report is
    scheduled separately (once a day, not on the same interval).
    """
    result = await db.execute(select(Business.id))
    counts = {"businesses": 0, "low_stock": 0, "stockouts": 0}
    for (business_id,) in result.all():
        counts["businesses"] += 1
        try:
            counts["low_stock"] += len(await scan_low_stock(db, business_id))
            counts["stockouts"] += len(await scan_forecasted_stockouts(db, business_id))
        except Exception:
            logger.exception("scheduled checks failed for business %s", business_id)
    return counts