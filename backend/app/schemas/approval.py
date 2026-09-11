import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import ApprovalStatus


class ApprovalDecision(BaseModel):
    decision_note: str | None = None


class ApprovalStepRead(BaseModel):
    id: uuid.UUID
    stage_number: int
    status: ApprovalStatus
    required_roles: list[str]
    resolved_by_user_id: uuid.UUID | None
    resolved_at: datetime | None
    decision_note: str | None
    created_at: datetime


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
    # Phase 9: multi-stage chain. required_stages = total sequential
    # approvals; current_stage = which one is awaiting a decision now
    # (1-based; == required_stages when the request is fully decided).
    required_stages: int
    current_stage: int
    steps: list[ApprovalStepRead]