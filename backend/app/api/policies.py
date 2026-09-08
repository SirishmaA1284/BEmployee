"""Business policies API (FR-16).

OWNER/ADMIN manage a business's policies; any member can read them. Policies
are evaluated deterministically by app/policies — the API only stores them.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.business_policy import BusinessPolicy
from app.models.enums import AuditAction, BusinessRole
from app.models.user import User
from app.schemas.policy import PolicyRead, PolicyUpsert
from app.security.dependencies import get_current_membership, get_current_user, require_role
from app.services.audit_service import record_audit

router = APIRouter(prefix="/api/policies", tags=["policies"])

_write_role = require_role(BusinessRole.OWNER, BusinessRole.ADMIN)


@router.get("", response_model=list[PolicyRead])
async def list_policies(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[PolicyRead]:
    result = await db.execute(
        select(BusinessPolicy)
        .where(BusinessPolicy.business_id == membership.business_id)
        .order_by(BusinessPolicy.key)
    )
    return [
        PolicyRead(
            id=p.id,
            policy_type=p.policy_type,
            key=p.key,
            value=p.value,
            description=p.description,
            is_active=p.is_active,
            updated_at=p.updated_at,
        )
        for p in result.scalars().all()
    ]


@router.put("/{key}", response_model=PolicyRead)
async def upsert_policy(
    key: str,
    payload: PolicyUpsert,
    membership: BusinessMember = Depends(_write_role),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PolicyRead:
    result = await db.execute(
        select(BusinessPolicy).where(
            BusinessPolicy.business_id == membership.business_id,
            BusinessPolicy.key == key,
        )
    )
    policy = result.scalar_one_or_none()

    if policy is None:
        policy = BusinessPolicy(
            business_id=membership.business_id,
            policy_type=payload.policy_type,
            key=key,
            value=payload.value,
            description=payload.description,
            is_active=payload.is_active,
            updated_by_user_id=current_user.id,
        )
        db.add(policy)
    else:
        policy.policy_type = payload.policy_type
        policy.value = payload.value
        policy.description = payload.description
        policy.is_active = payload.is_active
        policy.updated_by_user_id = current_user.id

    await record_audit(
        db,
        business_id=membership.business_id,
        actor_type="USER",
        actor_user_id=current_user.id,
        action=AuditAction.POLICY_UPSERT,
        target_type="business_policy",
        target_id=policy.id,
        summary=f"Upserted policy {key}",
        after={"policy_type": payload.policy_type.value, "value": payload.value, "is_active": payload.is_active},
    )
    await db.commit()
    await db.refresh(policy)
    return PolicyRead(
        id=policy.id,
        policy_type=policy.policy_type,
        key=policy.key,
        value=policy.value,
        description=policy.description,
        is_active=policy.is_active,
        updated_at=policy.updated_at,
    )
