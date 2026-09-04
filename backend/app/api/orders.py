import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.customer import Customer
from app.models.enums import BusinessRole, InvoiceStatus, OrderStatus, StockMovementReason
from app.models.inventory import Inventory
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.schemas.order import OrderCreate, OrderItemRead, OrderRead
from app.security.dependencies import get_current_membership, get_current_user, require_role
from app.services.inventory_service import is_stock_sufficient
from app.services.invoicing import format_invoice_number
from app.services.pricing import compute_tax, line_total, sum_amounts

router = APIRouter(prefix="/api/orders", tags=["orders"])

_cancel_role = require_role(BusinessRole.OWNER, BusinessRole.ADMIN)


async def _build_order_read(db: AsyncSession, order: Order) -> OrderRead:
    items_result = await db.execute(
        select(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
    )
    items = [
        OrderItemRead(
            product_id=product.id,
            sku=product.sku,
            product_name=product.name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item, product in items_result.all()
    ]

    invoice_result = await db.execute(select(Invoice).where(Invoice.order_id == order.id))
    invoice = invoice_result.scalar_one_or_none()

    customer = await db.get(Customer, order.customer_id)

    return OrderRead(
        id=order.id,
        customer_id=order.customer_id,
        customer_name=customer.name if customer else "",
        status=order.status,
        subtotal=order.subtotal,
        tax_amount=order.tax_amount,
        total=order.total,
        currency=order.currency,
        items=items,
        invoice_id=invoice.id if invoice else None,
        invoice_number=invoice.invoice_number if invoice else None,
        created_at=order.created_at,
    )


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    membership: BusinessMember = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    """OBSERVE -> UNDERSTAND -> PLAN -> EXECUTE for a single deterministic
    workflow, done synchronously in one DB transaction:
    validate customer/products -> check stock -> compute totals -> create
    order+items -> decrement inventory (+ log stock movements) -> generate
    invoice. All arithmetic is app/services/pricing.py, never inferred.
    """
    customer_result = await db.execute(
        select(Customer).where(
            Customer.id == payload.customer_id,
            Customer.business_id == membership.business_id,
            Customer.deleted_at.is_(None),
        )
    )
    customer = customer_result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # Merge duplicate product_id lines so "3 coffee, 2 coffee" in one
    # request is treated as one line of 5, not two independent stock checks.
    quantities: dict[uuid.UUID, int] = {}
    for line in payload.items:
        quantities[line.product_id] = quantities.get(line.product_id, 0) + line.quantity

    product_ids = list(quantities.keys())
    rows_result = await db.execute(
        select(Product, Inventory)
        .join(Inventory, Inventory.product_id == Product.id)
        .where(
            Product.id.in_(product_ids),
            Product.business_id == membership.business_id,
            Product.deleted_at.is_(None),
        )
    )
    rows = {product.id: (product, inventory) for product, inventory in rows_result.all()}

    missing = [str(pid) for pid in product_ids if pid not in rows]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product(s) not found: {', '.join(missing)}",
        )

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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Insufficient stock", "issues": insufficient},
        )

    business = await db.get(Business, membership.business_id)

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
        business_id=membership.business_id,
        customer_id=customer.id,
        status=OrderStatus.CONFIRMED,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total=total,
        currency=business.currency,
        created_by_user_id=current_user.id,
        items=order_items,
    )
    db.add(order)
    await db.flush()

    for product_id, quantity in quantities.items():
        _, inventory = rows[product_id]
        inventory.quantity_on_hand -= quantity
        db.add(
            StockMovement(
                business_id=membership.business_id,
                product_id=product_id,
                change_quantity=-quantity,
                reason=StockMovementReason.SALE,
                reference_type="order",
                reference_id=order.id,
                created_by_user_id=current_user.id,
            )
        )

    invoice_count_result = await db.execute(
        select(func.count()).select_from(Invoice).where(Invoice.business_id == membership.business_id)
    )
    next_sequence = invoice_count_result.scalar_one() + 1
    invoice = Invoice(
        business_id=membership.business_id,
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
    db.add(invoice)

    await db.commit()
    await db.refresh(order)
    return await _build_order_read(db, order)


@router.get("", response_model=list[OrderRead])
async def list_orders(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[OrderRead]:
    result = await db.execute(
        select(Order)
        .where(Order.business_id == membership.business_id)
        .order_by(Order.created_at.desc())
    )
    return [await _build_order_read(db, order) for order in result.scalars().all()]


async def _get_order_or_404(db: AsyncSession, business_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.business_id == business_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    order = await _get_order_or_404(db, membership.business_id, order_id)
    return await _build_order_read(db, order)


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: uuid.UUID,
    membership: BusinessMember = Depends(_cancel_role),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    order = await _get_order_or_404(db, membership.business_id, order_id)
    if order.status == OrderStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order is already cancelled")

    invoice_result = await db.execute(select(Invoice).where(Invoice.order_id == order.id))
    invoice = invoice_result.scalar_one_or_none()
    if invoice is not None and invoice.status == InvoiceStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot cancel an order whose invoice is already paid (refunds are not yet supported)",
        )

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    for item in items_result.scalars().all():
        inv_result = await db.execute(
            select(Inventory).where(
                Inventory.business_id == membership.business_id, Inventory.product_id == item.product_id
            )
        )
        inventory = inv_result.scalar_one()
        inventory.quantity_on_hand += item.quantity
        db.add(
            StockMovement(
                business_id=membership.business_id,
                product_id=item.product_id,
                change_quantity=item.quantity,
                reason=StockMovementReason.ORDER_CANCELLED,
                reference_type="order",
                reference_id=order.id,
                created_by_user_id=current_user.id,
            )
        )

    order.status = OrderStatus.CANCELLED
    if invoice is not None:
        invoice.status = InvoiceStatus.VOID

    await db.commit()
    await db.refresh(order)
    return await _build_order_read(db, order)
