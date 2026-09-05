"""Deterministic reporting math for the Finance/Reporting agent.

All numbers are computed in plain SQL/Python — the LLM only narrates them.
Phase 4 scope: a compact sales summary. Deeper reporting (period
comparisons, per-product margins) lands with Phase 6's scheduled daily
report, reusing these same functions.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InvoiceStatus, OrderStatus
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.payment import Payment


async def sales_summary(db: AsyncSession, business_id: uuid.UUID) -> dict:
    """One business's headline numbers: order/invoice counts, gross revenue,
    collected revenue, and outstanding receivables. Deterministic and
    unit-testable against seeded rows.
    """
    orders_result = await db.execute(
        select(func.count(), func.sum(Order.total)).where(
            Order.business_id == business_id, Order.status != OrderStatus.CANCELLED
        )
    )
    order_count, gross = orders_result.one()
    gross = gross or Decimal("0.00")

    invoiced_result = await db.execute(
        select(func.count(), func.sum(Invoice.total)).where(
            Invoice.business_id == business_id, Invoice.status != InvoiceStatus.VOID
        )
    )
    invoice_count, invoiced_total = invoiced_result.one()
    invoiced_total = invoiced_total or Decimal("0.00")

    paid_result = await db.execute(
        select(func.sum(Payment.amount)).where(Payment.business_id == business_id)
    )
    collected = paid_result.scalar_one() or Decimal("0.00")

    return {
        "order_count": order_count or 0,
        "gross_sales": str(gross),
        "invoice_count": invoice_count or 0,
        "invoiced_total": str(invoiced_total),
        "collected": str(collected),
        "outstanding": str(invoiced_total - collected),
    }