"""Seed/demo data (Phase 8, DoD "Seed/demo data exists").

`python -m app.seed` creates a demo business with realistic data so the app
can be explored immediately: an OWNER, products with inventory, customers,
suppliers with price links, a confirmed order with a paid invoice, a draft
purchase order, a low-stock product (so the worker/alerts have something to
find), and an uploaded document (so RAG works out of the box).

Deterministic and idempotent: re-running it finds the seeded owner by email
and creates nothing new (safe to run on an existing dev DB).
"""

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.customer import Customer
from app.models.enums import (
    BusinessRole,
    InvoiceStatus,
    OrderStatus,
    PaymentMethod,
    PurchaseOrderStatus,
)
from app.models.inventory import Inventory
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.models.user import User
from app.security.passwords import hash_password

DEMO_OWNER_EMAIL = "demo@example.com"
DEMO_OWNER_PASSWORD = "demo-strong-password"
DEMO_BUSINESS_NAME = "Demo Traders"

# (sku, name, unit, unit_price, cost, qty, threshold, reorder_qty)
PRODUCTS = [
    ("COF-500", "Coffee 500g", "unit", "450.00", "300.00", 42, 15, 40),
    ("SUG-1", "Sugar 1kg", "unit", "55.00", "40.00", 120, 30, 60),
    ("MLK-1", "Milk 1L", "unit", "60.00", "45.00", 8, 20, 24),  # low stock -> alert
    ("RCE-5", "Rice 5kg", "unit", "320.00", "240.00", 25, 10, 30),
    ("TL-1", "Tea 250g", "unit", "180.00", "120.00", 35, 12, 20),
]

CUSTOMERS = ["Rahul Sharma", "Priya Verma", "Amit Patel"]

SUPPLIERS = [
    ("Metro Wholesale", "500.00", 3),   # coffee
    ("Sunrise Foods", "55.00", 2),      # sugar
    ("Green Dairy", "60.00", 1),        # milk
]

DOCUMENT_TEXT = """Demo Traders — Return Policy

We accept returns within 30 days of purchase with a valid receipt.
Items must be in their original packaging and in resellable condition.
Perishable goods (milk, dairy) cannot be returned.

Store Hours

Monday to Saturday 9am to 8pm. Closed on Sundays.
Delivery is available within 5 km for orders above 500 rupees.
"""


async def _get_or_create_owner(db) -> tuple[User, Business, bool]:
    """Returns (owner, business, created). `created` is True only when the
    demo business was newly created — when it already exists, seeding skips
    everything (idempotent re-run)."""
    result = await db.execute(select(User).where(User.email == DEMO_OWNER_EMAIL))
    user = result.scalar_one_or_none()
    if user is not None:
        b_result = await db.execute(
            select(Business).where(Business.name == DEMO_BUSINESS_NAME)
        )
        business = b_result.scalar_one_or_none()
        return user, business, False

    user = User(
        email=DEMO_OWNER_EMAIL,
        hashed_password=hash_password(DEMO_OWNER_PASSWORD),
        full_name="Demo Owner",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    business = Business(name=DEMO_BUSINESS_NAME, currency="INR")
    db.add(business)
    await db.flush()
    db.add(BusinessMember(business_id=business.id, user_id=user.id, role=BusinessRole.OWNER))
    return user, business, True


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        owner, business, created = await _get_or_create_owner(db)
        if not created:
            print(f"Demo data already seeded (owner {DEMO_OWNER_EMAIL}). Nothing to do.")
            return
        business_id = business.id

        products = {}
        for sku, name, unit, price, cost, qty, threshold, reorder_qty in PRODUCTS:
            product = Product(
                business_id=business_id,
                sku=sku,
                name=name,
                unit=unit,
                unit_price=Decimal(price),
                cost_price=Decimal(cost),
                is_active=True,
            )
            db.add(product)
            await db.flush()
            db.add(
                Inventory(
                    business_id=business_id,
                    product_id=product.id,
                    quantity_on_hand=qty,
                    reorder_threshold=threshold,
                    reorder_quantity=reorder_qty,
                )
            )
            products[sku] = product

        customers = []
        for name in CUSTOMERS:
            customer = Customer(business_id=business_id, name=name)
            db.add(customer)
            await db.flush()
            customers.append(customer)

        suppliers = {}
        for (name, price, lead_time), sku in zip(SUPPLIERS, ["COF-500", "SUG-1", "MLK-1"]):
            supplier = Supplier(business_id=business_id, name=name, is_active=True)
            db.add(supplier)
            await db.flush()
            db.add(
                SupplierProduct(
                    business_id=business_id,
                    supplier_id=supplier.id,
                    product_id=products[sku].id,
                    price=Decimal(price),
                    lead_time_days=lead_time,
                )
            )
            suppliers[sku] = supplier

        # One confirmed order (paid) for Rahul: 3 coffee + 2 sugar.
        coffee = products["COF-500"]
        sugar = products["SUG-1"]
        order = Order(
            business_id=business_id,
            customer_id=customers[0].id,
            status=OrderStatus.CONFIRMED,
            subtotal=Decimal("1460.00"),
            tax_amount=Decimal("0.00"),
            total=Decimal("1460.00"),
            currency="INR",
            created_by_user_id=owner.id,
        )
        db.add(order)
        await db.flush()
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=coffee.id,
                quantity=3,
                unit_price=Decimal("450.00"),
                line_total=Decimal("1350.00"),
            )
        )
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=sugar.id,
                quantity=2,
                unit_price=Decimal("55.00"),
                line_total=Decimal("110.00"),
            )
        )
        invoice = Invoice(
            business_id=business_id,
            order_id=order.id,
            invoice_number="INV-000001",
            status=InvoiceStatus.PAID,
            subtotal=Decimal("1460.00"),
            tax_amount=Decimal("0.00"),
            total=Decimal("1460.00"),
        )
        db.add(invoice)
        await db.flush()
        db.add(
            Payment(
                business_id=business_id,
                invoice_id=invoice.id,
                amount=Decimal("1460.00"),
                method=PaymentMethod.UPI,
                recorded_by_user_id=owner.id,
            )
        )

        # A draft purchase order for low stock (milk) — shows in the PO list.
        milk = products["MLK-1"]
        po = PurchaseOrder(
            business_id=business_id,
            supplier_id=suppliers["MLK-1"].id,
            status=PurchaseOrderStatus.DRAFT,
            subtotal=Decimal("480.00"),
            total=Decimal("480.00"),
            created_by_user_id=owner.id,
        )
        db.add(po)
        await db.flush()
        db.add(
            PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=milk.id,
                quantity=8,
                unit_cost=Decimal("60.00"),
                line_total=Decimal("480.00"),
            )
        )

        # An uploaded document so RAG demos without manual upload.
        from app.models.document import Document, DocumentChunk
        from app.services.chunking import chunk_text

        doc = Document(
            business_id=business_id,
            filename="store-policy.txt",
            content_type="text/plain",
            size_bytes=len(DOCUMENT_TEXT.encode()),
            text_content=DOCUMENT_TEXT,
            title="Store policy",
            uploaded_by_user_id=owner.id,
        )
        db.add(doc)
        await db.flush()
        for index, chunk in enumerate(chunk_text(DOCUMENT_TEXT)):
            db.add(
                DocumentChunk(
                    document_id=doc.id,
                    business_id=business_id,
                    chunk_index=index,
                    content=chunk.content,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                )
            )

        await db.commit()
        print(
            f"Seeded demo business '{DEMO_BUSINESS_NAME}': "
            f"{len(PRODUCTS)} products, {len(CUSTOMERS)} customers, "
            f"{len(SUPPLIERS)} suppliers, 1 order+paid invoice, 1 draft PO, 1 document."
        )
        print(f"Log in at /login with {DEMO_OWNER_EMAIL} / {DEMO_OWNER_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())