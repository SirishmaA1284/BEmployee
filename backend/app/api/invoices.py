import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User
from app.schemas.invoice import InvoiceItemRead, InvoiceRead, PaymentCreate, PaymentRead
from app.security.dependencies import get_current_membership, get_current_user
from app.services.pricing import sum_amounts

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


async def _build_invoice_read(db: AsyncSession, invoice: Invoice) -> InvoiceRead:
    items_result = await db.execute(
        select(InvoiceItem, Product)
        .join(Product, Product.id == InvoiceItem.product_id)
        .where(InvoiceItem.invoice_id == invoice.id)
    )
    items = [
        InvoiceItemRead(
            product_id=product.id,
            sku=product.sku,
            product_name=product.name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item, product in items_result.all()
    ]

    payments_result = await db.execute(select(Payment.amount).where(Payment.invoice_id == invoice.id))
    amount_paid = sum_amounts(list(payments_result.scalars().all()))

    return InvoiceRead(
        id=invoice.id,
        order_id=invoice.order_id,
        invoice_number=invoice.invoice_number,
        status=invoice.status,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        total=invoice.total,
        amount_paid=amount_paid,
        amount_due=invoice.total - amount_paid,
        issued_at=invoice.issued_at,
        items=items,
    )


@router.get("", response_model=list[InvoiceRead])
async def list_invoices(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceRead]:
    result = await db.execute(
        select(Invoice)
        .where(Invoice.business_id == membership.business_id)
        .order_by(Invoice.issued_at.desc())
    )
    return [await _build_invoice_read(db, invoice) for invoice in result.scalars().all()]


async def _get_invoice_or_404(db: AsyncSession, business_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.business_id == business_id)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@router.get("/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(
    invoice_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRead:
    invoice = await _get_invoice_or_404(db, membership.business_id, invoice_id)
    return await _build_invoice_read(db, invoice)


@router.post("/{invoice_id}/payments", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
async def record_payment(
    invoice_id: uuid.UUID,
    payload: PaymentCreate,
    membership: BusinessMember = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRead:
    invoice = await _get_invoice_or_404(db, membership.business_id, invoice_id)
    if invoice.status == InvoiceStatus.VOID:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot pay a void invoice")

    payments_result = await db.execute(select(Payment.amount).where(Payment.invoice_id == invoice.id))
    already_paid = sum_amounts(list(payments_result.scalars().all()))
    if already_paid + payload.amount > invoice.total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Payment of {payload.amount} would exceed the amount due "
            f"({invoice.total - already_paid})",
        )

    db.add(
        Payment(
            business_id=membership.business_id,
            invoice_id=invoice.id,
            amount=payload.amount,
            method=payload.method,
            recorded_by_user_id=current_user.id,
        )
    )

    if already_paid + payload.amount == invoice.total:
        invoice.status = InvoiceStatus.PAID

    await db.commit()
    await db.refresh(invoice)
    return await _build_invoice_read(db, invoice)
