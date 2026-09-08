"""Unified audit log (FR-25, docs/decisions.md DoD Phase 5).

Every state-changing action — human or AI — writes one audit_logs row:
actor, action, target, business, timestamp, before/after summary. This is
the single cross-cutting trail on top of the domain tables' own immutable
history (stock_movements, agent_actions).

`actor_type` distinguishes a human USER action from an AGENT action (the
agent always acts under the requesting user's business/role context, so
`actor_user_id` is still populated). `target_type` is a domain name
("order", "purchase_order", ...) and `target_id` the affected row when one
exists. `before`/`after` hold compact JSON summaries of the pre/post state
for the action where relevant.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import AuditAction


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), default=None
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "USER" | "AGENT"
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, name="audit_action"), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
