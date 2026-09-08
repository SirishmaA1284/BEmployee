import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import PolicyType


class PolicyUpsert(BaseModel):
    policy_type: PolicyType
    key: str = Field(min_length=1, max_length=64)
    value: dict[str, Any]
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class PolicyRead(BaseModel):
    id: uuid.UUID
    policy_type: PolicyType
    key: str
    value: dict[str, Any]
    description: str | None
    is_active: bool
    updated_at: datetime
