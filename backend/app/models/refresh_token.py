"""Refresh tokens (Phase 8, docs/security.md MVP-hardening item).

A rotating opaque refresh token: `POST /api/auth/refresh` validates the
presented token, revokes it, and issues a new one — so a stolen refresh
token is usable only once and replay is detected. Only the SHA-256 hash is
stored; the plaintext token is shown exactly once (at issue time).

`replaced_by_id` links the rotation chain for audit. Logout revokes the
current token.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("uq_refresh_tokens_token_hash", "token_hash", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hex of the opaque token — never the raw token.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Previous token in this rotation chain (audit of rotation history).
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), default=None
    )
    # The IP that created the token (best-effort, for anomaly spotting).
    created_ip: Mapped[str | None] = mapped_column(String(64), default=None)