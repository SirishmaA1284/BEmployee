"""Business policies (FR-16, docs/decisions.md ADR-004).

A policy is a named, typed rule a business owner configures. The policy
engine (app/policies) evaluates these deterministically — the LLM never
interprets them. Each row carries a `key` unique per business and a
JSONB `value` whose shape is implied by `policy_type`.

Two policy types ship in Phase 5:
- MONEY_THRESHOLD: value = {"amount": Decimal string}; a proposed action
  whose computed money impact is >= amount is escalated MEDIUM -> HIGH.
- APPROVAL_ROLES: value = {"roles": [role codes]}; which roles may resolve
  an approval request at a given risk level. Defaults to OWNER/ADMIN when
  absent (docs/authorization.md).
"""

import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PolicyType


class BusinessPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_policies"
    __table_args__ = (
        UniqueConstraint("business_id", "key", name="uq_business_policies_business_key"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    policy_type: Mapped[PolicyType] = mapped_column(
        Enum(PolicyType, name="policy_type"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
