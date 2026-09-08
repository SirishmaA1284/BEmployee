import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import AuditAction


class AuditLogRead(BaseModel):
    id: uuid.UUID
    actor_type: str
    actor_user_id: uuid.UUID | None
    action: AuditAction
    target_type: str | None
    target_id: uuid.UUID | None
    summary: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime
