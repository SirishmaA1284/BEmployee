"""Order workflow: validate -> stock check -> create order+items ->
decrement inventory (logged) -> generate invoice, all in one transaction.

This is the deterministic core shared by the REST endpoint
(`POST /api/orders`) and the agent's `create_order` tool — the exact same
code path, so what a human can do through the API and what the AI employee
does through its tools is provably identical (docs/decisions.md ADR-003).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business
from app.models.customer import Customer
from app.models.enums import InvoiceStatus, OrderStatus, StockMovementReason
from app.models.inventory import Inventory
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.services.errors import BusinessRuleError
from app.services.inventory_service import is_stock_sufficient
from app.services.invoicing import format_invoice_number
from app.services.pricing import compute_tax, line_total, sum_amounts


async def create_order(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    customer_id: uuid.UUID,
    items: list[tuple[uuid.UUID, int]],
    created_by_user_id: uuid.UUID,
    business_currency: str | None = None,
) -> Order:
    """Creates a confirmed order with invoice, decrementing stock.

    `items` is a list of (product_id, quantity) pairs — duplicate products
    are merged by the caller (or here, if the caller passes them).
    Raises BusinessRuleError for unknown/inactive/insufficient-stock cases.
    """
    customer_result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.business_id == business_id,
            Customer.deleted_at.is_(None),
        )
    )
    customer = customer_result.scalar_one_or_none()
    if customer is None:
        raise BusinessRuleError(404, "Customer not found")

    quantities: dict[uuid.UUID, int] = {}
    for product_id, quantity in items:
        quantities[product_id] = quantities.get(product_id, 0) + quantity

    rows_result = await db.execute(
        select(Product, Inventory)
        .join(Inventory, Inventory.product_id == Product.id)
        .where(
            Product.id.in_(list(quantities.keys())),
            Product.business_id == business_id,
            Product.deleted_at.is_(None),
        )
    )
    rows = {product.id: (product, inventory) for product, inventory in rows_result.all()}

    missing = [str(pid) for pid in quantities if pid not in rows]
    if missing:
        raise BusinessRuleError(404, f"Product(s) not found: {', '.join(missing)}")

    insufficient = []
    for product_id, quantity in quantities.items():
        product, inventory = rows[product_id]
        if not product.is_active:
            insufficient.append(f"{product.sku} is inactive")
        elif not is_stock_sufficient(inventory.quantity_on_hand, quantity):
            insufficient.append(
                f"{product.sku}: requested {quantity}, available {inventory.quantity_on_hand}"
            )
    if insufficient:
        raise BusinessRuleError(
            422, {"message": "Insufficient stock", "issues": insufficient}
        )

    if business_currency is None:
        business = await db.get(Business, business_id)
        business_currency = business.currency if business else "INR"

    order_items: list[OrderItem] = []
    line_totals = []
    for product_id, quantity in quantities.items():
        product, _ = rows[product_id]
        item_total = line_total(quantity, product.unit_price)
        line_totals.append(item_total)
        order_items.append(
            OrderItem(
                product_id=product_id,
                quantity=quantity,
                unit_price=product.unit_price,
                line_total=item_total,
            )
        )

    subtotal = sum_amounts(line_totals)
    tax_amount = compute_tax(subtotal)
    total = subtotal + tax_amount

    order = Order(
        business_id=business_id,
        customer_id=customer.id,
        status=OrderStatus.CONFIRMED,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total=total,
        currency=business_currency,
        created_by_user_id=created_by_user_id,
        items=order_items,
    )
    db.add(order)
    await db.flush()

    for product_id, quantity in quantities.items():
        _, inventory = rows[product_id]
        inventory.quantity_on_hand -= quantity
        db.add(
            StockMovement(
                business_id=business_id,
                product_id=product_id,
                change_quantity=-quantity,
                reason=StockMovementReason.SALE,
                reference_type="order",
                reference_id=order.id,
                created_by_user_id=created_by_user_id,
            )
        )

    invoice_count_result = await db.execute(
        select(func.count()).select_from(Invoice).where(Invoice.business_id == business_id)
    )
    next_sequence = invoice_count_result.scalar_one() + 1
    db.add(
        Invoice(
            business_id=business_id,
            order_id=order.id,
            invoice_number=format_invoice_number(next_sequence),
            status=InvoiceStatus.ISSUED,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total=total,
            items=[
                InvoiceItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in order_items
            ],
        )
    )

    await db.commit()
    await db.refresh(order)
    return order