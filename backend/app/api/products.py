import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.enums import BusinessRole
from app.models.inventory import Inventory
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.security.dependencies import get_current_membership, require_role

router = APIRouter(prefix="/api/products", tags=["products"])

_write_role = require_role(BusinessRole.OWNER, BusinessRole.ADMIN)


async def _get_product_or_404(db: AsyncSession, business_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.business_id == business_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    existing = await db.execute(
        select(Product).where(
            Product.business_id == membership.business_id,
            Product.sku == payload.sku,
            Product.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="SKU already exists for this business"
        )

    product = Product(
        business_id=membership.business_id,
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        unit=payload.unit,
        unit_price=payload.unit_price,
        cost_price=payload.cost_price,
    )
    db.add(product)
    await db.flush()

    # Every product gets an inventory row at creation (qty 0) — inventory
    # is never a nullable/optional side-table a product can exist without.
    db.add(
        Inventory(
            business_id=membership.business_id,
            product_id=product.id,
            quantity_on_hand=0,
            reorder_threshold=payload.reorder_threshold,
            reorder_quantity=payload.reorder_quantity,
        )
    )
    await db.commit()
    await db.refresh(product)
    return ProductRead.model_validate(product)


@router.get("", response_model=list[ProductRead])
async def list_products(
    search: str | None = None,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ProductRead]:
    query = select(Product).where(
        Product.business_id == membership.business_id, Product.deleted_at.is_(None)
    )
    if search:
        pattern = f"%{search}%"
        query = query.where(Product.name.ilike(pattern) | Product.sku.ilike(pattern))
    result = await db.execute(query.order_by(Product.name))
    return [ProductRead.model_validate(p) for p in result.scalars().all()]


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    product = await _get_product_or_404(db, membership.business_id, product_id)
    return ProductRead.model_validate(product)


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    product = await _get_product_or_404(db, membership.business_id, product_id)

    updates = payload.model_dump(
        exclude_unset=True, exclude={"reorder_threshold", "reorder_quantity"}
    )
    for field, value in updates.items():
        setattr(product, field, value)

    if payload.reorder_threshold is not None or payload.reorder_quantity is not None:
        inv_result = await db.execute(
            select(Inventory).where(
                Inventory.business_id == membership.business_id,
                Inventory.product_id == product_id,
            )
        )
        inventory = inv_result.scalar_one()
        if payload.reorder_threshold is not None:
            inventory.reorder_threshold = payload.reorder_threshold
        if payload.reorder_quantity is not None:
            inventory.reorder_quantity = payload.reorder_quantity

    await db.commit()
    await db.refresh(product)
    return ProductRead.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> None:
    product = await _get_product_or_404(db, membership.business_id, product_id)
    product.deleted_at = utcnow()
    await db.commit()
