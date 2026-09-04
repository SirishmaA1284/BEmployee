import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.enums import BusinessRole
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from app.schemas.supplier import (
    SupplierCreate,
    SupplierPriceComparisonRow,
    SupplierProductCreate,
    SupplierProductRead,
    SupplierRead,
    SupplierUpdate,
)
from app.security.dependencies import get_current_membership, require_role
from app.services.procurement import rank_supplier_offers

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])

_write_role = require_role(BusinessRole.OWNER, BusinessRole.ADMIN)


async def _get_supplier_or_404(db: AsyncSession, business_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.business_id == business_id,
            Supplier.deleted_at.is_(None),
        )
    )
    supplier = result.scalar_one_or_none()
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return supplier


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> SupplierRead:
    supplier = Supplier(business_id=membership.business_id, **payload.model_dump())
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return SupplierRead.model_validate(supplier)


@router.get("", response_model=list[SupplierRead])
async def list_suppliers(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SupplierRead]:
    result = await db.execute(
        select(Supplier)
        .where(Supplier.business_id == membership.business_id, Supplier.deleted_at.is_(None))
        .order_by(Supplier.name)
    )
    return [SupplierRead.model_validate(s) for s in result.scalars().all()]


@router.get("/compare", response_model=list[SupplierPriceComparisonRow])
async def compare_supplier_prices(
    product_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SupplierPriceComparisonRow]:
    """Deterministic price/lead-time comparison for one product across all
    suppliers that offer it (spec: "Which supplier gives the best price").
    Ranking logic lives in app/services/procurement.py so Phase 4's
    Procurement Agent uses the exact same function, not a separate LLM
    judgment call.
    """
    result = await db.execute(
        select(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.business_id == membership.business_id,
            SupplierProduct.product_id == product_id,
            Supplier.deleted_at.is_(None),
        )
    )
    offers = [
        SupplierPriceComparisonRow(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            is_active=supplier.is_active,
            price=sp.price,
            lead_time_days=sp.lead_time_days,
        )
        for sp, supplier in result.all()
    ]
    return rank_supplier_offers(offers)


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_supplier(
    supplier_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> SupplierRead:
    supplier = await _get_supplier_or_404(db, membership.business_id, supplier_id)
    return SupplierRead.model_validate(supplier)


@router.patch("/{supplier_id}", response_model=SupplierRead)
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> SupplierRead:
    supplier = await _get_supplier_or_404(db, membership.business_id, supplier_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    await db.commit()
    await db.refresh(supplier)
    return SupplierRead.model_validate(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(
    supplier_id: uuid.UUID,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> None:
    supplier = await _get_supplier_or_404(db, membership.business_id, supplier_id)
    supplier.deleted_at = utcnow()
    await db.commit()


@router.post(
    "/{supplier_id}/products", response_model=SupplierProductRead, status_code=status.HTTP_201_CREATED
)
async def link_supplier_product(
    supplier_id: uuid.UUID,
    payload: SupplierProductCreate,
    membership: BusinessMember = Depends(_write_role),
    db: AsyncSession = Depends(get_db),
) -> SupplierProductRead:
    await _get_supplier_or_404(db, membership.business_id, supplier_id)

    product_result = await db.execute(
        select(Product).where(
            Product.id == payload.product_id,
            Product.business_id == membership.business_id,
            Product.deleted_at.is_(None),
        )
    )
    product = product_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    existing = await db.execute(
        select(SupplierProduct).where(
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.product_id == payload.product_id,
        )
    )
    link = existing.scalar_one_or_none()
    if link is None:
        link = SupplierProduct(
            business_id=membership.business_id,
            supplier_id=supplier_id,
            product_id=payload.product_id,
            price=payload.price,
            lead_time_days=payload.lead_time_days,
        )
        db.add(link)
    else:
        link.price = payload.price
        link.lead_time_days = payload.lead_time_days

    await db.commit()
    await db.refresh(link)
    return SupplierProductRead(
        id=link.id,
        supplier_id=link.supplier_id,
        product_id=link.product_id,
        sku=product.sku,
        product_name=product.name,
        price=link.price,
        lead_time_days=link.lead_time_days,
    )


@router.get("/{supplier_id}/products", response_model=list[SupplierProductRead])
async def list_supplier_products(
    supplier_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SupplierProductRead]:
    await _get_supplier_or_404(db, membership.business_id, supplier_id)
    result = await db.execute(
        select(SupplierProduct, Product)
        .join(Product, Product.id == SupplierProduct.product_id)
        .where(SupplierProduct.supplier_id == supplier_id)
    )
    return [
        SupplierProductRead(
            id=sp.id,
            supplier_id=sp.supplier_id,
            product_id=sp.product_id,
            sku=product.sku,
            product_name=product.name,
            price=sp.price,
            lead_time_days=sp.lead_time_days,
        )
        for sp, product in result.all()
    ]
