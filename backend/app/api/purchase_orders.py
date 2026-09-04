import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.enums import BusinessRole, PurchaseOrderStatus, StockMovementReason
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.stock_movement import StockMovement
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.models.user import User
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderItemRead, PurchaseOrderRead
from app.security.dependencies import get_current_membership, get_current_user, require_role
from app.services.pricing import line_total, sum_amounts

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])

# See docs/decisions.md ADR-015: full approval-gated lifecycle lands in
# Phase 5. Restricting every write to OWNER/ADMIN is an interim safeguard.
_write_role = require_role(BusinessRole.OWNER, BusinessRole.ADMIN)


async def _build_po_read(db: AsyncSession, po: PurchaseOrder) -> PurchaseOrderRead:
    items_result = await db.execute(
        select(PurchaseOrderItem, Product)
        .join(Product, Product.id == PurchaseOrderItem.product_id)
        .where(PurchaseOrderItem.purchase_order_id == po.id)
    )
    items = [
        PurchaseOrderItemRead(
            product_id=product.id,
            sku=product.sku,
            product_name=product.name,
            quantity=item.quantity,
            unit_cost=item.unit_cost,
            line_total=item.line_total,
        )
        for item, product in items_result.all()
    ]
    supplier = await db.get(Supplier, po.supplier_id)

    return PurchaseOrderRead(
        id=po.id,
        supplier_id=po.supplier_id,
        supplier_name=supplier.name if supplier else "",
        status=po.status,
        subtotal=po.subtotal,
        total=po.total,
        items=items,
        created_at=po.created_at,
        sent_at=po.sent_at,
        completed_at=po.completed_at,
    )


@router.post("", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    membership: BusinessMember = Depends(_write_role),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderRead:
    supplier_result = await db.execute(
        select(Supplier).where(
            Supplier.id == payload.supplier_id,
            Supplier.business_id == membership.business_id,
            Supplier.deleted_at.is_(None),
        )
    )
    supplier = supplier_result.scalar_one_or_none()
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    if not supplier.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot create a purchase order against an inactive supplier",
        )

    items: list[PurchaseOrderItem] = []
    line_totals = []
    for line in payload.items:
        product_result = await db.execute(
            select(Product).where(
                Product.id == line.product_id,
                Product.business_id == membership.business_id,
                Product.deleted_at.is_(None),
            )
        )
        product = product_result.scalar_one_or_none()
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {line.product_id} not found"
            )

        unit_cost = line.unit_cost
        if unit_cost is None:
            sp_result = await db.execute(
                select(SupplierProduct).where(
                    SupplierProduct.supplier_id == payload.supplier_id,
                    SupplierProduct.product_id == line.product_id,
                )
            )
            supplier_product = sp_result.scalar_one_or_none()
            if supplier_product is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"No on-file price for {product.sku} from this supplier — provide unit_cost",
                )
            unit_cost = supplier_product.price

        item_total = line_total(line.quantity, unit_cost)
        line_totals.append(item_total)
        items.append(
            PurchaseOrderItem(
                product_id=line.product_id,
                quantity=line.quantity,
                unit_cost=unit_cost,
                line_total=item_total,
            )
        )

    subtotal = sum_amounts(line_totals)
    po = PurchaseOrder(
        business_id=membership.business_id,
        supplier_id=payload.supplier_id,
        status=PurchaseOrderStatus.DRAFT,
        subtotal=subtotal,
        total=subtotal,
        created_by_user_id=current_user.id,
        items=items,
    )
    db.add(po)
    await db.commit()
    await db.refresh(po)
    return await _build_po_read(db, po)


@router.get("", response_model=list[PurchaseOrderRead])
async def list_purchase_orders(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[PurchaseOrderRead]:
    result = await db.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.business_id == membership.business_id)
        .order_by(PurchaseOrder.created_at.desc())
    )
    return [await _build_po_read(db, po) for po in result.scalars().all()]


async def _get_po_or_404(db: AsyncSession, business_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder:
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.id == po_id, PurchaseOrder.business_id == business_id
        )
    )
    po = result.scalar_one_or_none()
    if po is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return po


@router.get("/{po_id}", response_model=PurchaseOrderRead)
async def get_purchase_order(
    po_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderRead:
    po = await _get_po_or_404(db, membership.business_id, po_id)
    return await _build_po_read(db, po)


@router.post("/{po_id}/send", response_model=PurchaseOrderRead)
async def send_purchase_order(
    po_id: uuid.UUID,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderRead:
    po = await _get_po_or_404(db, membership.business_id, po_id)
    if po.status != PurchaseOrderStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot send a purchase order in status {po.status.value}",
        )
    po.status = PurchaseOrderStatus.SENT
    po.sent_at = utcnow()
    await db.commit()
    await db.refresh(po)
    return await _build_po_read(db, po)


@router.post("/{po_id}/receive", response_model=PurchaseOrderRead)
async def receive_purchase_order(
    po_id: uuid.UUID,
    membership: BusinessMember = Depends(_write_role),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderRead:
    """Marks the PO COMPLETED and receives the full ordered quantity of
    every line into inventory. Partial receipt is not supported in MVP
    (documented roadmap item) — see docs/decisions.md.
    """
    po = await _get_po_or_404(db, membership.business_id, po_id)
    if po.status != PurchaseOrderStatus.SENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot receive a purchase order in status {po.status.value}",
        )

    items_result = await db.execute(
        select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po.id)
    )
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
                reason=StockMovementReason.PURCHASE_RECEIPT,
                reference_type="purchase_order",
                reference_id=po.id,
                created_by_user_id=current_user.id,
            )
        )

    po.status = PurchaseOrderStatus.COMPLETED
    po.completed_at = utcnow()
    await db.commit()
    await db.refresh(po)
    return await _build_po_read(db, po)


@router.post("/{po_id}/cancel", response_model=PurchaseOrderRead)
async def cancel_purchase_order(
    po_id: uuid.UUID,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> PurchaseOrderRead:
    po = await _get_po_or_404(db, membership.business_id, po_id)
    if po.status == PurchaseOrderStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot cancel a completed purchase order"
        )
    if po.status == PurchaseOrderStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already cancelled")
    po.status = PurchaseOrderStatus.CANCELLED
    await db.commit()
    await db.refresh(po)
    return await _build_po_read(db, po)
