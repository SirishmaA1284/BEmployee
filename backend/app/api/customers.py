import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.security.dependencies import get_current_membership

router = APIRouter(prefix="/api/customers", tags=["customers"])

# Any role can create/edit customers — "routine operations" per spec §4.


async def _get_customer_or_404(db: AsyncSession, business_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.business_id == business_id,
            Customer.deleted_at.is_(None),
        )
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    customer = Customer(business_id=membership.business_id, **payload.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return CustomerRead.model_validate(customer)


@router.get("", response_model=list[CustomerRead])
async def list_customers(
    search: str | None = None,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerRead]:
    query = select(Customer).where(
        Customer.business_id == membership.business_id, Customer.deleted_at.is_(None)
    )
    if search:
        query = query.where(Customer.name.ilike(f"%{search}%"))
    result = await db.execute(query.order_by(Customer.name))
    return [CustomerRead.model_validate(c) for c in result.scalars().all()]


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    customer = await _get_customer_or_404(db, membership.business_id, customer_id)
    return CustomerRead.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    customer = await _get_customer_or_404(db, membership.business_id, customer_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    await db.commit()
    await db.refresh(customer)
    return CustomerRead.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer_or_404(db, membership.business_id, customer_id)
    customer.deleted_at = utcnow()
    await db.commit()
