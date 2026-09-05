"""Purchase order creation (draft lifecycle).

Shared by `POST /api/purchase-orders` and the agent's
`create_purchase_order` tool so both paths enforce identical rules:
active supplier, product exists in this business, and price comes from
`supplier_products` unless an explicit `unit_cost` override is given.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PurchaseOrderStatus
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.services.errors import BusinessRuleError
from app.services.pricing import line_total, sum_amounts


async def create_purchase_order(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    supplier_id: uuid.UUID,
    items: list[tuple[uuid.UUID, int, uuid.UUID | None]],
    created_by_user_id: uuid.UUID,
) -> PurchaseOrder:
    """Creates a DRAFT purchase order.

    `items` is a list of (product_id, quantity, unit_cost_or_none) — a None
    unit cost falls back to the supplier's on-file price for that product.
    """
    supplier_result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.business_id == business_id,
            Supplier.deleted_at.is_(None),
        )
    )
    supplier = supplier_result.scalar_one_or_none()
    if supplier is None:
        raise BusinessRuleError(404, "Supplier not found")
    if not supplier.is_active:
        raise BusinessRuleError(422, "Cannot create a purchase order against an inactive supplier")

    po_items: list[PurchaseOrderItem] = []
    line_totals = []
    for product_id, quantity, unit_cost in items:
        product_result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.business_id == business_id,
                Product.deleted_at.is_(None),
            )
        )
        product = product_result.scalar_one_or_none()
        if product is None:
            raise BusinessRuleError(404, f"Product {product_id} not found")

        if unit_cost is None:
            sp_result = await db.execute(
                select(SupplierProduct).where(
                    SupplierProduct.supplier_id == supplier_id,
                    SupplierProduct.product_id == product_id,
                )
            )
            supplier_product = sp_result.scalar_one_or_none()
            if supplier_product is None:
                raise BusinessRuleError(
                    422,
                    f"No on-file price for {product.sku} from this supplier — provide unit_cost",
                )
            unit_cost = supplier_product.price

        item_total = line_total(quantity, unit_cost)
        line_totals.append(item_total)
        po_items.append(
            PurchaseOrderItem(
                product_id=product_id,
                quantity=quantity,
                unit_cost=unit_cost,
                line_total=item_total,
            )
        )

    subtotal = sum_amounts(line_totals)
    po = PurchaseOrder(
        business_id=business_id,
        supplier_id=supplier_id,
        status=PurchaseOrderStatus.DRAFT,
        subtotal=subtotal,
        total=subtotal,
        created_by_user_id=created_by_user_id,
        items=po_items,
    )
    db.add(po)
    await db.commit()
    await db.refresh(po)
    return po