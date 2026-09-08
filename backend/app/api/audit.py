"""Audit log API (FR-25).

Read-only view of a business's unified audit trail. Any member can read the
log for observability; only the backend writes it.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.audit import AuditLog
from app.models.business_member import BusinessMember
from app.schemas.audit import AuditLogRead
from app.security.dependencies import get_current_membership

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
async def list_audit_logs(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
) -> list[AuditLogRead]:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.business_id == membership.business_id)
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 500))
    )
    return [
        AuditLogRead(
            id=log.id,
            actor_type=log.actor_type,
            actor_user_id=log.actor_user_id,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            summary=log.summary,
            before=log.before,
            after=log.after,
            created_at=log.created_at,
        )
        for log in result.scalars().all()
    ]
