"""Notifications API (FR-24).

Read-only view of a business's notifications (low stock, forecasted
stockouts, pending approvals, daily report). Any member can read them;
creation happens in the worker / backend, never via this API.

Phase 9: per-user read state. `GET /api/notifications` returns each
notification's `read` flag for the current member and can filter to unread
only; `POST /api/notifications/{id}/read` and `POST
/api/notifications/read-all` mark notifications read for that member.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.enums import NotificationChannel, NotificationType
from app.models.notification import Notification, NotificationReadState
from app.models.user import User
from app.schemas.notification import NotificationRead
from app.security.dependencies import get_current_membership, get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


async def _read_ids(db: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    result = await db.execute(
        select(NotificationReadState.notification_id).where(
            NotificationReadState.user_id == user_id
        )
    )
    return set(result.scalars().all())


def _to_read(notification: Notification, read_ids: set[uuid.UUID]) -> NotificationRead:
    return NotificationRead(
        id=notification.id,
        notification_type=notification.notification_type,
        severity=notification.severity,
        channel=notification.channel,
        title=notification.title,
        message=notification.message,
        payload=notification.payload,
        target_type=notification.target_type,
        target_id=notification.target_id,
        created_at=notification.created_at,
        read=notification.id in read_ids,
    )


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    membership: BusinessMember = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    type_filter: NotificationType | None = None,
    in_app_only: bool = True,
    unread_only: bool = False,
    limit: int = 100,
) -> list[NotificationRead]:
    statement = select(Notification).where(
        Notification.business_id == membership.business_id
    )
    if in_app_only:
        statement = statement.where(Notification.channel == NotificationChannel.IN_APP)
    if type_filter is not None:
        statement = statement.where(Notification.notification_type == type_filter)
    if unread_only:
        read_subq = select(NotificationReadState.notification_id).where(
            NotificationReadState.user_id == current_user.id
        )
        statement = statement.where(Notification.id.not_in(read_subq))
    statement = statement.order_by(Notification.created_at.desc()).limit(min(limit, 500))
    result = await db.execute(statement)
    read_ids = await _read_ids(db, current_user.id)
    return [_to_read(n, read_ids) for n in result.scalars().all()]


async def _get_owned_notification(
    db: AsyncSession, membership: BusinessMember, notification_id: uuid.UUID
) -> Notification:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.business_id == membership.business_id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    return notification


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mark one notification read by the current member (idempotent)."""
    await _get_owned_notification(db, membership, notification_id)
    exists = await db.execute(
        select(NotificationReadState.notification_id).where(
            NotificationReadState.notification_id == notification_id,
            NotificationReadState.user_id == current_user.id,
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(
            NotificationReadState(
                notification_id=notification_id, user_id=current_user.id
            )
        )
    await db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(
    membership: BusinessMember = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mark every in-app notification of the business read by the member."""
    result = await db.execute(
        select(Notification.id).where(
            Notification.business_id == membership.business_id,
            Notification.channel == NotificationChannel.IN_APP,
        )
    )
    for notification_id in result.scalars().all():
        exists = await db.execute(
            select(NotificationReadState.notification_id).where(
                NotificationReadState.notification_id == notification_id,
                NotificationReadState.user_id == current_user.id,
            )
        )
        if exists.scalar_one_or_none() is None:
            db.add(
                NotificationReadState(
                    notification_id=notification_id, user_id=current_user.id
                )
            )
    await db.commit()