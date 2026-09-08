"""Rotating refresh-token lifecycle (Phase 8, docs/security.md).

Issue -> (validate + rotate) -> revoke. Tokens are opaque random strings;
only their SHA-256 hash is stored. Validation requires: exists, not revoked,
not expired. On success the presented token is revoked and a fresh one
issued (rotation), so a reused/leaked refresh token is rejected on the
second use — rotation is the replay defense.

`user_id` is always resolved server-side from the token row, never from a
request body.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.base import utcnow
from app.models.refresh_token import RefreshToken
from app.services.errors import BusinessRuleError


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(48)


def _expires_at() -> datetime:
    return utcnow() + timedelta(days=get_settings().refresh_token_expire_days)


async def issue_refresh_token(
    db: AsyncSession, *, user_id: uuid.UUID, created_ip: str | None = None
) -> tuple[str, RefreshToken]:
    """Create a new refresh token for a user. Returns (plaintext_token, row)."""
    token = _new_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=_hash(token),
        expires_at=_expires_at(),
        created_ip=created_ip,
    )
    db.add(row)
    await db.flush()
    return token, row


async def _row_for_token(db: AsyncSession, token: str) -> RefreshToken | None:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(token))
    )
    return result.scalar_one_or_none()


async def rotate_refresh_token(
    db: AsyncSession, *, token: str, created_ip: str | None = None
) -> tuple[str, RefreshToken, uuid.UUID]:
    """Validate a refresh token, revoke it, and issue a replacement.

    Returns (new_plaintext, new_row, user_id). Raises BusinessRuleError(401)
    when the token is unknown, revoked, or expired (constant message — no
    oracle about which case).
    """
    row = await _row_for_token(db, token)
    now = utcnow()
    if (
        row is None
        or row.revoked_at is not None
        or row.expires_at < now
    ):
        raise BusinessRuleError(401, "Refresh token is invalid or expired")

    new_token, new_row = await issue_refresh_token(
        db, user_id=row.user_id, created_ip=created_ip
    )
    row.revoked_at = now
    row.replaced_by_id = new_row.id
    return new_token, new_row, row.user_id


async def revoke_refresh_token(db: AsyncSession, *, token: str) -> None:
    """Revoke a refresh token (logout / explicit revoke). Idempotent —
    revoking an already-revoked or unknown token is a no-op (204).
    """
    row = await _row_for_token(db, token)
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()