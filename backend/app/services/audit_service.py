"""Unified audit log writer (FR-25).

Every state-changing action — human or AI — goes through `record_audit` to
write one audit_logs row. The registry (agent path) and the REST API (human
path) both call this; `actor_type` distinguishes "USER" from "AGENT" (an
agent always acts under the requesting user's business/role context, so
`actor_user_id` is still populated).

Keeping this a thin service means adding coverage to a new write path is a
one-line call, and the audit write is intentionally part of the same DB
session/transaction as the action it records (never best-effort fire-and-
forget).
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.enums import AuditAction


async def record_audit(
    db: AsyncSession,
    *,
    business_id: uuid.UUID | None,
    actor_type: str,  # "USER" | "AGENT"
    actor_user_id: uuid.UUID | None,
    action: AuditAction,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    summary: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditLog:
    log = AuditLog(
        business_id=business_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        before=before,
        after=after,
        request_id=request_id,
    )
    db.add(log)
    return log
