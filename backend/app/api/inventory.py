import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.enums import BusinessRole, StockMovementReason
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.schemas.inventory import InventoryRead, StockAdjustmentRequest
from app.security.dependencies import get_current_membership, get_current_user, require_role
from app.services.inventory_service import is_low_stock

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

_write_role = require_role(BusinessRole.OWNER, BusinessRole.ADMIN)


def _to_read(inventory: Inventory, product: Product) -> InventoryRead:
    return InventoryRead(
        product_id=product.id,
        sku=product.sku,
        product_name=product.name,
        quantity_on_hand=inventory.quantity_on_hand,
        reorder_threshold=inventory.reorder_threshold,
        reorder_quantity=inventory.reorder_quantity,
        is_low_stock=is_low_stock(inventory.quantity_on_hand, inventory.reorder_threshold),
    )


@router.get("", response_model=list[InventoryRead])
async def list_inventory(
    low_stock_only: bool = False,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[InventoryRead]:
    result = await db.execute(
        select(Inventory, Product)
        .join(Product, Product.id == Inventory.product_id)
        .where(Inventory.business_id == membership.business_id, Product.deleted_at.is_(None))
        .order_by(Product.name)
    )
    rows = [_to_read(inv, product) for inv, product in result.all()]
    if low_stock_only:
        rows = [row for row in rows if row.is_low_stock]
    return rows


async def _get_inventory_or_404(
    db: AsyncSession, business_id: uuid.UUID, product_id: uuid.UUID
) -> tuple[Inventory, Product]:
    result = await db.execute(
        select(Inventory, Product)
        .join(Product, Product.id == Inventory.product_id)
        .where(Inventory.business_id == business_id, Inventory.product_id == product_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return row


@router.get("/{product_id}", response_model=InventoryRead)
async def get_inventory(
    product_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> InventoryRead:
    inventory, product = await _get_inventory_or_404(db, membership.business_id, product_id)
    return _to_read(inventory, product)


@router.post("/{product_id}/adjust", response_model=InventoryRead)
async def adjust_inventory(
    product_id: uuid.UUID,
    payload: StockAdjustmentRequest,
    membership: BusinessMember = Depends(_write_role),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InventoryRead:
    """Manual stock correction (stock take, damage, etc). Every adjustment
    is logged as a StockMovement — inventory.quantity_on_hand is never
    edited without a corresponding audit row (spec FR-6).

    Approval gating for this action is not yet wired up (Phase 5) — see
    docs/decisions.md ADR-016; restricting to OWNER/ADMIN is an interim
    safeguard.
    """
    inventory, product = await _get_inventory_or_404(db, membership.business_id, product_id)

    new_quantity = inventory.quantity_on_hand + payload.change_quantity
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Adjustment would result in negative stock ({new_quantity})",
        )

    inventory.quantity_on_hand = new_quantity
    db.add(
        StockMovement(
            business_id=membership.business_id,
            product_id=product_id,
            change_quantity=payload.change_quantity,
            reason=StockMovementReason.ADJUSTMENT,
            note=payload.note,
            created_by_user_id=current_user.id,
        )
    )
    await db.commit()
    await db.refresh(inventory)
    return _to_read(inventory, product)
