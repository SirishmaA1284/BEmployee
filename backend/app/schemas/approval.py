import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import ApprovalStatus


class ApprovalDecision(BaseModel):
    decision_note: str | None = None


class ApprovalRequestRead(BaseModel):
    id: uuid.UUID
    action: str
    summary: str | None
    payload: dict[str, Any]
    risk_level: str
    target_type: str | None
    target_id: uuid.UUID | None
    status: ApprovalStatus
    requested_by_user_id: uuid.UUID
    resolved_by_user_id: uuid.UUID | None
    resolved_at: datetime | None
    decision_note: str | None
    created_at: datetime
