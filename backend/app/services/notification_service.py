"""Notification creation + mock messaging (FR-24, docs/decisions.md A6).

`notify` writes the IN_APP row (always) and, when a channel other than
IN_APP is requested, records a second row on the MOCK channel that logs the
"sent" message. No real WhatsApp/SMS/email provider is contacted — A6 keeps
the MVP runnable without credentials; the mock rows make the delivery
attempt observable in the audit trail.

Creators: the scheduled worker (low stock, stockouts, daily report) and the
backend for events a human should see (pending approval). All content is
backend-generated, never LLM.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AuditAction,
    NotificationChannel,
    NotificationSeverity,
    NotificationType,
)
from app.models.notification import Notification
from app.services.audit_service import record_audit

logger = logging.getLogger(__name__)


async def notify(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    notification_type: NotificationType,
    severity: NotificationSeverity,
    title: str,
    message: str,
    payload: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    channel: NotificationChannel = NotificationChannel.IN_APP,
    actor_user_id: uuid.UUID | None = None,
) -> Notification:
    """Create a notification (and, for non-IN_APP channels, a mock delivery
    row). Returns the IN_APP notification row.
    """
    notification = Notification(
        business_id=business_id,
        notification_type=notification_type,
        severity=severity,
        channel=channel,
        title=title,
        message=message,
        payload=payload,
        target_type=target_type,
        target_id=target_id,
    )
    db.add(notification)
    await db.flush()

    if channel != NotificationChannel.IN_APP:
        mock = Notification(
            business_id=business_id,
            notification_type=notification_type,
            severity=severity,
            channel=channel,
            title=title,
            message=f"[mock {channel.value.lower()} delivery] {message}",
            payload={**(payload or {}), "delivery": "mock"},
            target_type=target_type,
            target_id=target_id,
        )
        db.add(mock)
        logger.info("mock %s delivery for business %s: %s", channel.value, business_id, title)

    await record_audit(
        db,
        business_id=business_id,
        actor_type="AGENT",
        actor_user_id=actor_user_id,
        action=AuditAction.NOTIFICATION_SENT,
        target_type=target_type or "notification",
        target_id=notification.id,
        summary=f"Sent {severity.value} {notification_type.value} notification: {title}",
        after={"channel": channel.value, "type": notification_type.value},
    )
    return notification