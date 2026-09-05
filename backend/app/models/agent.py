"""Agent observability models (FR-14/FR-15).

agent_sessions  — one chat request (user message -> reply)
agent_tasks     — the workflow (graph) run for that request
agent_actions   — every tool call made by the workflow, with a concise
                  input/output summary, risk level and status

Rules (docs/decisions.md ADR-003, FR-14): actions store summaries, never
raw chain-of-thought; every state-changing tool call is persisted here
structurally by the tool registry — agent code cannot write without going
through the registry, and the registry cannot execute without recording.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import (
    AgentActionStatus,
    AgentIntent,
    AgentSessionStatus,
    AgentTaskStatus,
)


class AgentSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_sessions"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    intent: Mapped[AgentIntent | None] = mapped_column(
        Enum(AgentIntent, name="agent_intent"), default=None
    )
    status: Mapped[AgentSessionStatus] = mapped_column(
        Enum(AgentSessionStatus, name="agent_session_status"),
        default=AgentSessionStatus.RUNNING,
        nullable=False,
    )
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    reply: Mapped[str | None] = mapped_column(Text, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    tasks: Mapped[list["AgentTask"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AgentTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_tasks"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[AgentTaskStatus] = mapped_column(
        Enum(AgentTaskStatus, name="agent_task_status"),
        default=AgentTaskStatus.RUNNING,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    session: Mapped["AgentSession"] = relationship(back_populates="tasks")
    actions: Mapped[list["AgentAction"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class AgentAction(UUIDPrimaryKeyMixin, Base):
    """One registry tool execution. No updated_at — an audit row is never
    edited after the fact (same rule as stock_movements).
    """

    __tablename__ = "agent_actions"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AgentActionStatus] = mapped_column(
        Enum(AgentActionStatus, name="agent_action_status"), nullable=False
    )
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    input_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    task: Mapped["AgentTask"] = relationship(back_populates="actions")