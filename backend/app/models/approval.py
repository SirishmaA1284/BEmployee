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

Phase 9 — multi-stage (chained) approval: `required_stages` counts the
sequential approvals the business's APPROVAL_STAGES policy requires (default
1 = a single decision, Phase 5 behavior). Each stage is an `ApprovalStep`
row resolved one at a time, in order; the request stays PENDING until every
stage is APPROVED. Consecutive stages must be decided by different people
(one user cannot rubber-stamp the whole chain).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import ApprovalStatus


class ApprovalStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One sequential decision in a multi-stage approval request (Phase 9).

    Steps are resolved in `stage_number` order; the request only completes
    when every step is APPROVED. Each step records who decided and when, so
    the chain is fully auditable per approver.
    """

    __tablename__ = "approval_request_steps"

    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    stage_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status"),
        default=ApprovalStatus.PENDING,
        nullable=False,
    )
    # Roles allowed to decide this stage (copied from APPROVAL_ROLES at
    # request creation so later policy edits don't change an open request).
    required_roles: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decision_note: Mapped[str | None] = mapped_column(Text, default=None)

    approval_request: Mapped["ApprovalRequest"] = relationship(back_populates="steps")


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
    # Phase 9: number of sequential approval stages required (default 1).
    required_stages: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    steps: Mapped[list[ApprovalStep]] = relationship(
        back_populates="approval_request",
        cascade="all, delete-orphan",
        order_by="ApprovalStep.stage_number",
    )
