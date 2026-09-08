"""Approval requests (FR-18, docs/decisions.md ADR-004).

When a proposed action is HIGH risk (or policy-flagged), the system creates
an ApprovalRequest and stops before execution. The request records the
intended action and arguments; a human resolves it via the API. There is no
code path for an agent to approve its own request — `resolved_by_user_id`
is always the authenticated human who decided, and the actor who created
the request can be anyone (a user or, via the agent, the requesting user).

`target_type`/`target_id` are set once the action can be tied to a concrete
row (e.g. a purchase order created in PENDING_APPROVAL). For write actions
that don't yet have a target id (e.g. an order that must be approved before
execution), `target_id` is null and `payload` holds the proposed arguments.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import ApprovalStatus


class ApprovalRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    # What is being approved: a domain action name (e.g. "create_purchase_order").
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # Summary of the proposed action for the human reviewer (never raw chain-of-thought).
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    # The proposed arguments / payload. Stored so approval -> execution can
    # replay the exact intended action without trusting a later prompt.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)

    # Optional link to a concrete target once it exists (e.g. a PO in PENDING_APPROVAL).
    target_type: Mapped[str | None] = mapped_column(String(64), default=None)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"),
        default=ApprovalStatus.PENDING,
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decision_note: Mapped[str | None] = mapped_column(Text, default=None)
