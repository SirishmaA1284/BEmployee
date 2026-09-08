"""Deterministic demand forecasting (FR-13, FR-24, docs/decisions.md ADR-013).

All numbers are computed in plain Python/SQL from the order history — never
by the LLM. The worker and any agent narration only *display* these values.

Design:
- Daily sales series per product from `order_items` joined to non-cancelled
  `orders`, bucketed by UTC day.
- Projection = simple moving average over the trailing `window_days` of sales
  (default 14). Products with no sales in the window project to zero demand.
- Forecasted stockout date = today + ceil(quantity_on_hand / projected_daily)
  using the projected daily demand, and `days_until_stockout` is compared
  against the best (shortest) lead time across the product's active supplier
  offers so the worker can flag "will run out before a reorder can arrive".

The module is kept free of ORM row classes in its math so the pure functions
are unit-testable without a database; only the `*_for_business` queries need
a session.
"""

import math
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct

WINDOW_DAYS = 14


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def moving_average_daily_demand(
    daily_sales: dict[date, int], window_days: int = WINDOW_DAYS, today: date | None = None
) -> Decimal:
    """Projected daily demand = mean of per-day quantities sold in the trailing
    window. Days with no sales count as 0 (they are real demand information).
    An empty series projects to 0 — never a guess.
    """
    today = today or _today_utc()
    start = today - timedelta(days=window_days - 1)
    total = 0
    for offset in range(window_days):
        day = start + timedelta(days=offset)
        total += daily_sales.get(day, 0)
    return Decimal(total) / Decimal(window_days)


def project_days_until_stockout(
    quantity_on_hand: int, daily_demand: Decimal
) -> int | None:
    """Days until stock runs out at a constant projected demand, rounded up.
    Returns None when demand is zero (never stockouts) or on-hand is already
    0 (reported as 0 — already out).
    """
    if quantity_on_hand <= 0:
        return 0
    if daily_demand <= 0:
        return None
    return math.ceil(Decimal(quantity_on_hand) / daily_demand)


def forecast_stockout(
    product: Product,
    inventory: Inventory,
    daily_sales: dict[date, int],
    lead_time_days: int | None,
    *,
    window_days: int = WINDOW_DAYS,
    today: date | None = None,
) -> dict:
    """One product's forecast row. `lead_time_days` is the shortest active
    supplier lead time for the product (None when the business has no offer
    on file). Returns a JSON-safe dict for the worker / API.
    """
    today = today or _today_utc()
    daily_demand = moving_average_daily_demand(daily_sales, window_days, today)
    days_until_stockout = project_days_until_stockout(
        inventory.quantity_on_hand, daily_demand
    )

    stockout_date: date | None = None
    at_risk = False
    if days_until_stockout is not None:
        stockout_date = today + timedelta(days=days_until_stockout)
        # At risk when it will run out before the fastest reorder could arrive.
        if lead_time_days is not None and days_until_stockout <= lead_time_days:
            at_risk = True

    return {
        "product_id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "quantity_on_hand": inventory.quantity_on_hand,
        "reorder_threshold": inventory.reorder_threshold,
        "projected_daily_demand": str(daily_demand),
        "days_until_stockout": days_until_stockout,
        "stockout_date": stockout_date.isoformat() if stockout_date else None,
        "best_lead_time_days": lead_time_days,
        "at_risk": at_risk,
    }


async def daily_sales_series(
    db: AsyncSession, business_id: uuid.UUID, *, days: int = WINDOW_DAYS
) -> dict[uuid.UUID, dict[date, int]]:
    """Per-product daily sales series for the trailing `days` days (default
    window). Only non-cancelled orders count; a cancelled order must not
    project demand it never realised.
    """
    start = datetime.combine(_today_utc() - timedelta(days=days - 1), datetime.min.time(), tzinfo=timezone.utc)
    result = await db.execute(
        select(OrderItem.product_id, OrderItem.quantity, Order.created_at)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.business_id == business_id,
            Order.status != OrderStatus.CANCELLED,
            Order.created_at >= start,
        )
    )
    series: dict[uuid.UUID, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for product_id, quantity, created_at in result.all():
        series[product_id][created_at.date()] += quantity
    return series


async def _shortest_lead_times(
    db: AsyncSession, business_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Shortest active supplier lead time per product for the business. Only
    active, non-deleted suppliers' offers count — a supplier you can't order
    from today can't rescue a stockout.
    """
    result = await db.execute(
        select(SupplierProduct.product_id, SupplierProduct.lead_time_days)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.business_id == business_id,
            Supplier.deleted_at.is_(None),
            Supplier.is_active.is_(True),
        )
    )
    best: dict[uuid.UUID, int] = {}
    for product_id, lead_time in result.all():
        if product_id not in best or lead_time < best[product_id]:
            best[product_id] = lead_time
    return best


async def forecast_for_business(
    db: AsyncSession,
    business_id: uuid.UUID,
    *,
    window_days: int = WINDOW_DAYS,
    at_risk_only: bool = False,
) -> list[dict]:
    """Forecast every active product of a business: projected daily demand,
    days until stockout, and at-risk flag. Used by the scheduled stockout
    scan and by any read endpoint the worker feeds.
    """
    series = await daily_sales_series(db, business_id, days=window_days)
    lead_times = await _shortest_lead_times(db, business_id)

    result = await db.execute(
        select(Product, Inventory)
        .join(Inventory, Inventory.product_id == Product.id)
        .where(Product.business_id == business_id, Product.deleted_at.is_(None))
    )
    rows: list[dict] = []
    for product, inventory in result.all():
        row = forecast_stockout(
            product,
            inventory,
            series.get(product.id, {}),
            lead_times.get(product.id),
            window_days=window_days,
        )
        if at_risk_only and not row["at_risk"]:
            continue
        rows.append(row)
    return rows