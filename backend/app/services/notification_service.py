"""Notification creation + messaging dispatch (FR-24, docs/decisions.md A6).

`notify` writes the IN_APP row (always) and then dispatches to messaging
channels:

- When a real channel (TELEGRAM/WHATSAPP) is requested explicitly and its
  credentials are configured, the message is sent via the real provider
  (`app/services/messaging.py`) and a delivery row on that channel records
  the attempt (with the provider's message id or error).
- When the channel is not configured, the MOCK_* channel row is written as
  before — the "sent" message is logged but no provider is contacted.
- When no channel is requested (default IN_APP), the row is dispatched to
  every configured real channel (env-driven); with nothing configured only
  the IN_APP row is created, so an unconfigured app behaves exactly as the
  A6 mock.

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
from app.services.messaging import (
    _delivery_text,
    send_telegram_message,
    send_whatsapp_message,
    telegram_configured,
    whatsapp_configured,
)

logger = logging.getLogger(__name__)

# Explicitly-requested channel -> (real channel, mock fallback channel).
_CHANNEL_MAP: dict[NotificationChannel, tuple[NotificationChannel | None, NotificationChannel]] = {
    NotificationChannel.TELEGRAM: (NotificationChannel.TELEGRAM, NotificationChannel.MOCK_TELEGRAM),
    NotificationChannel.WHATSAPP: (NotificationChannel.WHATSAPP, NotificationChannel.MOCK_WHATSAPP),
    NotificationChannel.MOCK_TELEGRAM: (None, NotificationChannel.MOCK_TELEGRAM),
    NotificationChannel.MOCK_WHATSAPP: (None, NotificationChannel.MOCK_WHATSAPP),
    NotificationChannel.MOCK_SMS: (None, NotificationChannel.MOCK_SMS),
    NotificationChannel.MOCK_EMAIL: (None, NotificationChannel.MOCK_EMAIL),
}


def _enabled_delivery_channels() -> list[NotificationChannel]:
    """Real channels configured in env, dispatched for every notification."""
    channels: list[NotificationChannel] = []
    if telegram_configured():
        channels.append(NotificationChannel.TELEGRAM)
    if whatsapp_configured():
        channels.append(NotificationChannel.WHATSAPP)
    return channels


async def _deliver(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    channel: NotificationChannel,
    notification_type: NotificationType,
    severity: NotificationSeverity,
    title: str,
    message: str,
    payload: dict[str, Any] | None,
    target_type: str | None,
    target_id: uuid.UUID | None,
) -> None:
    """Send one notification over a real channel (or record the mock row)."""
    real_channel, mock_channel = _CHANNEL_MAP.get(
        channel, (None, NotificationChannel.MOCK_WHATSAPP)
    )
    text = _delivery_text(title, message)

    if real_channel == NotificationChannel.TELEGRAM and telegram_configured():
        result = await send_telegram_message(text)
        delivery = "telegram"
    elif real_channel == NotificationChannel.WHATSAPP and whatsapp_configured():
        result = await send_whatsapp_message(text)
        delivery = "whatsapp"
    else:
        mock = Notification(
            business_id=business_id,
            notification_type=notification_type,
            severity=severity,
            channel=mock_channel,
            title=title,
            message=f"[mock {mock_channel.value.lower()} delivery] {message}",
            payload={**(payload or {}), "delivery": "mock"},
            target_type=target_type,
            target_id=target_id,
        )
        db.add(mock)
        logger.info("mock %s delivery for business %s: %s", channel.value, business_id, title)
        return

    sent = result.get("ok", False)
    db.add(
        Notification(
            business_id=business_id,
            notification_type=notification_type,
            severity=severity,
            channel=channel,
            title=title,
            message=message,
            payload={
                **(payload or {}),
                "delivery": delivery,
                "sent": sent,
                "error": result.get("error"),
                "provider_message_id": result.get("message_id"),
            },
            target_type=target_type,
            target_id=target_id,
        )
    )
    logger.info(
        "%s delivery for business %s: %s (ok=%s)", delivery, business_id, title, sent
    )


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
    """Create a notification (IN_APP row always) and dispatch to the requested
    or configured messaging channels. Returns the IN_APP notification row.
    """
    notification = Notification(
        business_id=business_id,
        notification_type=notification_type,
        severity=severity,
        channel=NotificationChannel.IN_APP,
        title=title,
        message=message,
        payload=payload,
        target_type=target_type,
        target_id=target_id,
    )
    db.add(notification)
    await db.flush()

    if channel != NotificationChannel.IN_APP:
        delivery_channels = [channel]
    else:
        delivery_channels = _enabled_delivery_channels()

    for delivery_channel in delivery_channels:
        await _deliver(
            db,
            business_id=business_id,
            channel=delivery_channel,
            notification_type=notification_type,
            severity=severity,
            title=title,
            message=message,
            payload=payload,
            target_type=target_type,
            target_id=target_id,
        )

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