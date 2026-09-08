"""Notifications (FR-24, docs/decisions.md ADR-007 / A6).

Created by the scheduled worker (low stock, forecasted stockouts, daily
report) and by the backend for events a human should see (pending approval
requests). `IN_APP` notifications are always written; MOCK_* channel rows
record a mock "sent" message so the MVP needs no real messaging provider
credentials (assumption A6).

A notification row is immutable once created (no `updated_at`) — it is an
audit-style record of *what was flagged and when*. Read state lives in the
frontend / read-model, not on the row.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import NotificationChannel, NotificationSeverity, NotificationType


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type"), nullable=False
    )
    severity: Mapped[NotificationSeverity] = mapped_column(
        Enum(NotificationSeverity, name="notification_severity"),
        default=NotificationSeverity.INFO,
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel"),
        default=NotificationChannel.IN_APP,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON-safe details (product ids, forecast values, links) the UI renders.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    # Optional link to the triggering domain row.
    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)