import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    AgentActionStatus,
    AgentIntent,
    AgentSessionStatus,
    AgentTaskStatus,
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    intent: AgentIntent
    agent_name: str
    status: AgentSessionStatus
    reply: str
    result: dict[str, Any] | None = None


class AgentSessionSummary(BaseModel):
    id: uuid.UUID
    intent: AgentIntent | None
    agent_name: str | None
    status: AgentSessionStatus
    user_message: str
    reply: str | None
    created_at: datetime


class AgentActionRead(BaseModel):
    id: uuid.UUID
    tool_name: str
    status: AgentActionStatus
    risk_level: str
    input_summary: dict[str, Any]
    result_summary: dict[str, Any]
    created_at: datetime


class AgentTaskRead(BaseModel):
    id: uuid.UUID
    agent_name: str | None
    status: AgentTaskStatus
    started_at: datetime
    completed_at: datetime | None
    actions: list[AgentActionRead]


class AgentSessionDetail(BaseModel):
    id: uuid.UUID
    intent: AgentIntent | None
    status: AgentSessionStatus
    user_message: str
    reply: str | None
    created_at: datetime
    completed_at: datetime | None
    tasks: list[AgentTaskRead]