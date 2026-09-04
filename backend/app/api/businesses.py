from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business import Business
from app.models.business_member import BusinessMember
from app.models.enums import BusinessRole
from app.models.user import User
from app.schemas.business import (
    BusinessCreate,
    BusinessMemberInvite,
    BusinessMemberRead,
    BusinessRead,
)
from app.security.dependencies import get_current_membership, get_current_user, require_role

router = APIRouter(prefix="/api/businesses", tags=["businesses"])


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
async def create_business(
    payload: BusinessCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BusinessRead:
    business = Business(name=payload.name, currency=payload.currency)
    db.add(business)
    await db.flush()

    membership = BusinessMember(
        business_id=business.id, user_id=current_user.id, role=BusinessRole.OWNER
    )
    db.add(membership)
    await db.commit()
    await db.refresh(business)

    return BusinessRead(
        id=business.id, name=business.name, currency=business.currency, role=BusinessRole.OWNER
    )


@router.get("", response_model=list[BusinessRead])
async def list_my_businesses(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[BusinessRead]:
    result = await db.execute(
        select(Business, BusinessMember.role)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(BusinessMember.user_id == current_user.id)
    )
    return [
        BusinessRead(id=b.id, name=b.name, currency=b.currency, role=role)
        for b, role in result.all()
    ]


@router.get("/members", response_model=list[BusinessMemberRead])
async def list_members(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[BusinessMemberRead]:
    # Any member of the business (any role) can see who else has access.
    result = await db.execute(
        select(BusinessMember, User)
        .join(User, User.id == BusinessMember.user_id)
        .where(BusinessMember.business_id == membership.business_id)
    )
    return [
        BusinessMemberRead(
            id=member.id, user_id=user.id, email=user.email, full_name=user.full_name, role=member.role
        )
        for member, user in result.all()
    ]


@router.post("/members", response_model=BusinessMemberRead, status_code=status.HTTP_201_CREATED)
async def invite_member(
    payload: BusinessMemberInvite,
    membership: BusinessMember = Depends(require_role(BusinessRole.OWNER)),
    db: AsyncSession = Depends(get_db),
) -> BusinessMemberRead:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No registered user with this email. They must register first.",
        )

    existing = await db.execute(
        select(BusinessMember).where(
            BusinessMember.business_id == membership.business_id,
            BusinessMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User is already a member of this business"
        )

    new_member = BusinessMember(
        business_id=membership.business_id, user_id=user.id, role=payload.role
    )
    db.add(new_member)
    await db.commit()
    await db.refresh(new_member)

    return BusinessMemberRead(
        id=new_member.id, user_id=user.id, email=user.email, full_name=user.full_name, role=new_member.role
    )
