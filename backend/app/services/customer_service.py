"""Customer creation helpers (Phase 10).

`find_or_create_customer` backs both the REST inline-customer order flow and
the agent's `create_customer` tool, so a new customer mentioned in an order
is added automatically instead of failing the order. Dedupe guards against
duplicate customers on repeat orders: an existing non-deleted customer wins
when the name matches case-insensitively, the phone matches (digits-only
normalization), or the email matches (case-insensitive). Returns
`(customer, created)` so callers can audit/narrate accurately.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


async def find_or_create_customer(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    name: str,
    phone: str | None = None,
    email: str | None = None,
) -> tuple[Customer, bool]:
    """Returns an existing matching customer, or creates one.

    Matching (in priority order): exact case-insensitive name, normalized
    phone, case-insensitive email. Only non-deleted customers match, and
    only when the caller actually provided the identifying value.
    """
    name = name.strip()
    phone = (phone or "").strip() or None
    email = (email or "").strip() or None
    if not name:
        raise ValueError("Customer name is required")

    result = await db.execute(
        select(Customer).where(
            Customer.business_id == business_id,
            Customer.deleted_at.is_(None),
        )
    )
    for existing in result.scalars().all():
        if existing.name.strip().lower() == name.lower():
            return existing, False
        if phone and existing.phone and _normalize_phone(existing.phone) == _normalize_phone(phone):
            return existing, False
        if email and existing.email and existing.email.strip().lower() == email.lower():
            return existing, False

    customer = Customer(
        business_id=business_id,
        name=name,
        phone=phone,
        email=email,
    )
    db.add(customer)
    await db.flush()
    return customer, True