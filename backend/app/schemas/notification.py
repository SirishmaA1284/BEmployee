import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import NotificationChannel, NotificationSeverity, NotificationType


class NotificationRead(BaseModel):
    id: uuid.UUID
    notification_type: NotificationType
    severity: NotificationSeverity
    channel: NotificationChannel
    title: str
    message: str
    payload: dict[str, Any] | None
    target_type: str | None
    target_id: uuid.UUID | None
    created_at: datetime