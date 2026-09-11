"""The Phase 4 tool catalog: every tool the AI employee may call.

Each handler is a thin adapter: validate via the schema (already done by the
registry), then delegate to `app/services` for deterministic business logic
or plain scoped reads. Handlers never trust the caller's ids — every query
is filtered by the business_id the registry passed in.

Tools the agents use that are NOT here (intent classification, entity
extraction) are prompt-layer calls, not data-access tools; they never touch
the database (docs/agents.md).
"""

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.enums import BusinessRole
from app.models.inventory import Inventory
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.policies.risk import RiskLevel
from app.services.customer_service import find_or_create_customer
from app.services.errors import BusinessRuleError
from app.services.inventory_service import is_low_stock
from app.services.order_service import create_order as create_order_service
from app.services.procurement import rank_supplier_offers
from app.services.purchase_order_service import create_purchase_order as create_po_service
from app.services.reporting import sales_summary
from app.tools.base import ToolError, ToolSpec
from app.tools.registry import registry


class SearchProductsArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class GetProductArgs(BaseModel):
    product_id: uuid.UUID


class SearchCustomersArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class CreateCustomerArgs(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)


class CheckStockArgs(BaseModel):
    search: str | None = Field(default=None, max_length=200)
    low_stock_only: bool = False


class CompareSupplierPricesArgs(BaseModel):
    product_id: uuid.UUID


class SearchSuppliersArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class OrderItemArgs(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class CreateOrderArgs(BaseModel):
    customer_id: uuid.UUID
    items: list[OrderItemArgs] = Field(min_length=1)


class PurchaseOrderItemArgs(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class CreatePurchaseOrderArgs(BaseModel):
    supplier_id: uuid.UUID
    items: list[PurchaseOrderItemArgs] = Field(min_length=1)


class GetOrderArgs(BaseModel):
    order_id: uuid.UUID


class NoArgs(BaseModel):
    """Tools that take no arguments (list/report). Keeps the registry's
    validate-before-execute rule uniform — even no-arg tools are validated.
    """


async def _product_rows(
    db: AsyncSession, business_id: uuid.UUID, query: str | None = None
) -> list[tuple[Product, Inventory]]:
    statement = (
        select(Product, Inventory)
        .join(Inventory, Inventory.product_id == Product.id)
        .where(Product.business_id == business_id, Product.deleted_at.is_(None))
    )
    if query:
        pattern = f"%{query}%"
        statement = statement.where(Product.name.ilike(pattern) | Product.sku.ilike(pattern))
    result = await db.execute(statement.order_by(Product.name))
    return [(p, i) for p, i in result.all()]


async def search_products(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: SearchProductsArgs
) -> dict:
    rows = await _product_rows(db, business_id, args.query)
    return {
        "count": len(rows),
        "products": [
            {
                "product_id": str(p.id),
                "sku": p.sku,
                "name": p.name,
                "unit": p.unit,
                "unit_price": str(p.unit_price),
                "is_active": p.is_active,
            }
            for p, _ in rows
        ],
    }


async def get_product(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: GetProductArgs
) -> dict:
    result = await db.execute(
        select(Product, Inventory)
        .join(Inventory, Inventory.product_id == Product.id)
        .where(Product.id == args.product_id, Product.business_id == business_id)
    )
    row = result.first()
    if row is None:
        raise ToolError(f"Product {args.product_id} not found")
    product, inventory = row
    return {
        "product_id": str(product.id),
        "sku": product.sku,
        "name": product.name,
        "unit": product.unit,
        "unit_price": str(product.unit_price),
        "is_active": product.is_active,
        "quantity_on_hand": inventory.quantity_on_hand,
        "reorder_threshold": inventory.reorder_threshold,
        "reorder_quantity": inventory.reorder_quantity,
        "is_low_stock": is_low_stock(inventory.quantity_on_hand, inventory.reorder_threshold),
    }


async def search_customers(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: SearchCustomersArgs
) -> dict:
    result = await db.execute(
        select(Customer)
        .where(
            Customer.business_id == business_id,
            Customer.deleted_at.is_(None),
            Customer.name.ilike(f"%{args.query}%"),
        )
        .order_by(Customer.name)
    )
    customers = [
        {
            "customer_id": str(c.id),
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
        }
        for c in result.scalars().all()
    ]
    return {"count": len(customers), "customers": customers}


async def create_customer(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: CreateCustomerArgs
) -> dict:
    """Find-or-create a customer (deduped by name/phone/email). Idempotent:
    calling it again with the same customer returns the existing row, so an
    agent can safely auto-create customers mentioned in orders without ever
    duplicating them.
    """
    customer, created = await find_or_create_customer(
        db,
        business_id=business_id,
        name=args.name,
        phone=args.phone,
        email=args.email,
    )
    return {
        "customer_id": str(customer.id),
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "created": created,
    }


async def check_stock(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: CheckStockArgs
) -> dict:
    rows = await _product_rows(db, business_id, args.search)
    items = [
        {
            "product_id": str(p.id),
            "sku": p.sku,
            "product_name": p.name,
            "quantity_on_hand": inv.quantity_on_hand,
            "reorder_threshold": inv.reorder_threshold,
            "reorder_quantity": inv.reorder_quantity,
            "is_low_stock": is_low_stock(inv.quantity_on_hand, inv.reorder_threshold),
        }
        for p, inv in rows
    ]
    if args.low_stock_only:
        items = [item for item in items if item["is_low_stock"]]
    return {"count": len(items), "items": items}


async def list_low_stock(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: CheckStockArgs
) -> dict:
    """Alias used by the low-stock workflow; same deterministic math as the
    `low_stock_only` filter on check_stock.
    """
    return await check_stock(db, business_id, user_id, CheckStockArgs(low_stock_only=True))


async def compare_supplier_prices(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: CompareSupplierPricesArgs
) -> dict:
    result = await db.execute(
        select(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.business_id == business_id,
            SupplierProduct.product_id == args.product_id,
            Supplier.deleted_at.is_(None),
        )
    )
    offers = [
        {
            "supplier_id": str(supplier.id),
            "supplier_name": supplier.name,
            "is_active": supplier.is_active,
            "price": str(sp.price),
            "lead_time_days": sp.lead_time_days,
        }
        for sp, supplier in result.all()
    ]
    # Same deterministic ranking the /api/suppliers/compare endpoint uses
    # (app/services/procurement.py) — the AI's recommendation is provably
    # the same one a human would see.
    ranked = sorted(
        offers, key=lambda offer: (not offer["is_active"], Decimal(offer["price"]), offer["lead_time_days"])
    )
    return {"count": len(ranked), "offers": ranked}


async def search_suppliers(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: SearchSuppliersArgs
) -> dict:
    result = await db.execute(
        select(Supplier)
        .where(
            Supplier.business_id == business_id,
            Supplier.deleted_at.is_(None),
            Supplier.name.ilike(f"%{args.query}%"),
        )
        .order_by(Supplier.name)
    )
    suppliers = [
        {"supplier_id": str(s.id), "name": s.name, "is_active": s.is_active}
        for s in result.scalars().all()
    ]
    return {"count": len(suppliers), "suppliers": suppliers}


async def _order_summary(db: AsyncSession, business_id: uuid.UUID, order: Order) -> dict:
    items_result = await db.execute(
        select(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
    )
    items = [
        {
            "product_id": str(item.product_id),
            "sku": product.sku,
            "name": product.name,
            "quantity": item.quantity,
            "unit_price": str(item.unit_price),
            "line_total": str(item.line_total),
        }
        for item, product in items_result.all()
    ]
    invoice_result = await db.execute(select(Invoice).where(Invoice.order_id == order.id))
    invoice = invoice_result.scalar_one_or_none()
    return {
        "order_id": str(order.id),
        "status": order.status.value,
        "subtotal": str(order.subtotal),
        "tax_amount": str(order.tax_amount),
        "total": str(order.total),
        "currency": order.currency,
        "invoice_id": str(invoice.id) if invoice else None,
        "invoice_number": invoice.invoice_number if invoice else None,
        "items": items,
    }


async def create_order(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: CreateOrderArgs
) -> dict:
    try:
        order = await create_order_service(
            db,
            business_id=business_id,
            customer_id=args.customer_id,
            items=[(item.product_id, item.quantity) for item in args.items],
            created_by_user_id=user_id,
        )
    except BusinessRuleError as exc:
        raise ToolError(exc.detail) from exc
    return await _order_summary(db, business_id, order)


async def list_orders(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: NoArgs
) -> dict:
    result = await db.execute(
        select(Order)
        .where(Order.business_id == business_id)
        .order_by(Order.created_at.desc())
        .limit(20)
    )
    orders = [await _order_summary(db, business_id, order) for order in result.scalars().all()]
    return {"count": len(orders), "orders": orders}


async def get_order(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: GetOrderArgs
) -> dict:
    result = await db.execute(
        select(Order).where(Order.id == args.order_id, Order.business_id == business_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise ToolError(f"Order {args.order_id} not found")
    return await _order_summary(db, business_id, order)


async def _po_summary(db: AsyncSession, business_id: uuid.UUID, po: PurchaseOrder) -> dict:
    items_result = await db.execute(
        select(PurchaseOrderItem, Product)
        .join(Product, Product.id == PurchaseOrderItem.product_id)
        .where(PurchaseOrderItem.purchase_order_id == po.id)
    )
    items = [
        {
            "product_id": str(item.product_id),
            "sku": product.sku,
            "name": product.name,
            "quantity": item.quantity,
            "unit_cost": str(item.unit_cost),
            "line_total": str(item.line_total),
        }
        for item, product in items_result.all()
    ]
    return {
        "purchase_order_id": str(po.id),
        "supplier_id": str(po.supplier_id),
        "status": po.status.value,
        "subtotal": str(po.subtotal),
        "total": str(po.total),
        "items": items,
    }


async def create_purchase_order(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: CreatePurchaseOrderArgs
) -> dict:
    try:
        po = await create_po_service(
            db,
            business_id=business_id,
            supplier_id=args.supplier_id,
            items=[(item.product_id, item.quantity, item.unit_cost) for item in args.items],
            created_by_user_id=user_id,
        )
    except BusinessRuleError as exc:
        raise ToolError(exc.detail) from exc
    return await _po_summary(db, business_id, po)


async def list_purchase_orders(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: NoArgs
) -> dict:
    result = await db.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.business_id == business_id)
        .order_by(PurchaseOrder.created_at.desc())
        .limit(20)
    )
    pos = [await _po_summary(db, business_id, po) for po in result.scalars().all()]
    return {"count": len(pos), "purchase_orders": pos}


async def get_sales_report(
    db: AsyncSession, business_id: uuid.UUID, user_id: uuid.UUID, args: NoArgs
) -> dict:
    return await sales_summary(db, business_id)


def register_catalog() -> None:
    registry.register(
        ToolSpec(
            name="search_products",
            description="Search the product catalog by name or SKU. Returns matching products "
            "with ids, prices and active status.",
            input_schema=SearchProductsArgs,
            risk_level=RiskLevel.LOW,
            handler=search_products,
        )
    )
    registry.register(
        ToolSpec(
            name="get_product",
            description="Get one product's details including current stock levels and reorder "
            "thresholds, by product_id.",
            input_schema=GetProductArgs,
            risk_level=RiskLevel.LOW,
            handler=get_product,
        )
    )
    registry.register(
        ToolSpec(
            name="search_customers",
            description="Search customers by name. Returns customer ids used to place orders.",
            input_schema=SearchCustomersArgs,
            risk_level=RiskLevel.LOW,
            handler=search_customers,
        )
    )
    registry.register(
        ToolSpec(
            name="create_customer",
            description="Add a customer (or find the existing one with the same name/phone/email). "
            "Safe to call for any customer mentioned in a request — never duplicates.",
            input_schema=CreateCustomerArgs,
            risk_level=RiskLevel.MEDIUM,
            handler=create_customer,
            action_summary="Added a customer",
        )
    )
    registry.register(
        ToolSpec(
            name="check_stock",
            description="List current inventory levels. Optionally filter to one product search "
            "or to low-stock items only.",
            input_schema=CheckStockArgs,
            risk_level=RiskLevel.LOW,
            handler=check_stock,
        )
    )
    registry.register(
        ToolSpec(
            name="list_low_stock",
            description="List products at or below their reorder threshold.",
            input_schema=CheckStockArgs,
            risk_level=RiskLevel.LOW,
            handler=list_low_stock,
        )
    )
    registry.register(
        ToolSpec(
            name="compare_supplier_prices",
            description="Compare all suppliers' offers (price, lead time) for one product, "
            "ranked best-first.",
            input_schema=CompareSupplierPricesArgs,
            risk_level=RiskLevel.LOW,
            handler=compare_supplier_prices,
        )
    )
    registry.register(
        ToolSpec(
            name="search_suppliers",
            description="Search suppliers by name. Returns supplier ids used for purchase orders.",
            input_schema=SearchSuppliersArgs,
            risk_level=RiskLevel.LOW,
            handler=search_suppliers,
        )
    )
    registry.register(
        ToolSpec(
            name="create_order",
            description="Create a customer order: checks stock, decrements inventory, and "
            "generates an invoice in one transaction.",
            input_schema=CreateOrderArgs,
            risk_level=RiskLevel.MEDIUM,
            handler=create_order,
            action_summary="Created a customer order",
        )
    )
    registry.register(
        ToolSpec(
            name="list_orders",
            description="List the most recent customer orders for this business.",
            input_schema=NoArgs,
            risk_level=RiskLevel.LOW,
            handler=list_orders,
        )
    )
    registry.register(
        ToolSpec(
            name="get_order",
            description="Get one customer order's details by order_id.",
            input_schema=GetOrderArgs,
            risk_level=RiskLevel.LOW,
            handler=get_order,
        )
    )
    registry.register(
        ToolSpec(
            name="create_purchase_order",
            description="Create a draft purchase order against a supplier. Uses the supplier's "
            "on-file prices unless a unit_cost is given.",
            input_schema=CreatePurchaseOrderArgs,
            risk_level=RiskLevel.MEDIUM,
            required_roles=(BusinessRole.OWNER, BusinessRole.ADMIN),
            handler=create_purchase_order,
            action_summary="Created a purchase order",
        )
    )
    registry.register(
        ToolSpec(
            name="list_purchase_orders",
            description="List the most recent purchase orders for this business.",
            input_schema=NoArgs,
            risk_level=RiskLevel.LOW,
            handler=list_purchase_orders,
        )
    )
    registry.register(
        ToolSpec(
            name="get_sales_report",
            description="Get a sales summary: order count, gross sales, invoiced total, "
            "collected and outstanding amounts.",
            input_schema=NoArgs,
            risk_level=RiskLevel.LOW,
            handler=get_sales_report,
        )
    )


register_catalog()