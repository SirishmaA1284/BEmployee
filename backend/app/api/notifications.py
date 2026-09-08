"""Notifications API (FR-24).

Read-only view of a business's notifications (low stock, forecasted
stockouts, pending approvals, daily report). Any member can read them;
creation happens in the worker / backend, never via this API.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.enums import NotificationChannel, NotificationType
from app.models.notification import Notification
from app.schemas.notification import NotificationRead
from app.security.dependencies import get_current_membership

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    type_filter: NotificationType | None = None,
    in_app_only: bool = True,
    limit: int = 100,
) -> list[NotificationRead]:
    statement = select(Notification).where(
        Notification.business_id == membership.business_id
    )
    if in_app_only:
        statement = statement.where(Notification.channel == NotificationChannel.IN_APP)
    if type_filter is not None:
        statement = statement.where(Notification.notification_type == type_filter)
    statement = statement.order_by(Notification.created_at.desc()).limit(min(limit, 500))
    result = await db.execute(statement)
    return [
        NotificationRead(
            id=n.id,
            notification_type=n.notification_type,
            severity=n.severity,
            channel=n.channel,
            title=n.title,
            message=n.message,
            payload=n.payload,
            target_type=n.target_type,
            target_id=n.target_id,
            created_at=n.created_at,
        )
        for n in result.scalars().all()
    ]