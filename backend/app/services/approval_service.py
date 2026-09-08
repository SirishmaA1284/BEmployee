"""Approval request lifecycle (FR-18).

- `create_approval_request` is called by the tool registry whenever a HIGH
  risk action is proposed: it records the pending request and the registry
  STOPS before execution.
- `decide` is the human, authenticated decision path. It checks the
  resolver's role against the business's APPROVAL_ROLES policy for the
  request's risk level (defaulting to OWNER/ADMIN). There is no code path
  for an agent (or the requester) to approve their own request.

When an approved request targets a purchase order that was created in
PENDING_APPROVAL, `decide` also transitions that PO to APPROVED (FR-9).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.models.approval import ApprovalRequest
from app.models.business_policy import BusinessPolicy
from app.models.enums import ApprovalStatus, AuditAction, PurchaseOrderStatus
from app.models.purchase_order import PurchaseOrder
from app.policies.policies import approval_roles_for
from app.policies.risk import RiskLevel
from app.services.audit_service import record_audit
from app.services.errors import BusinessRuleError


async def create_approval_request(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    action: str,
    payload: dict[str, Any],
    risk_level: str,
    requested_by_user_id: uuid.UUID,
    summary: str | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    approval = ApprovalRequest(
        business_id=business_id,
        action=action,
        summary=summary,
        payload=payload,
        risk_level=risk_level,
        target_type=target_type,
        target_id=target_id,
        requested_by_user_id=requested_by_user_id,
    )
    db.add(approval)
    await db.flush()
    return approval


async def _approval_roles(db: AsyncSession, business_id: uuid.UUID, risk_level: str) -> list[str]:
    result = await db.execute(
        select(BusinessPolicy).where(
            BusinessPolicy.business_id == business_id, BusinessPolicy.is_active.is_(True)
        )
    )
    return approval_roles_for(list(result.scalars().all()), RiskLevel(risk_level))


async def decide(
    db: AsyncSession,
    *,
    approval_id: uuid.UUID,
    business_id: uuid.UUID,
    resolver_user_id: uuid.UUID,
    resolver_role: str,
    approve: bool,
    decision_note: str | None = None,
) -> ApprovalRequest:
    """Resolves a PENDING approval request as a human decision."""
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id, ApprovalRequest.business_id == business_id
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise BusinessRuleError(404, "Approval request not found")
    if approval.status != ApprovalStatus.PENDING:
        raise BusinessRuleError(409, f"Approval request is already {approval.status.value}")

    allowed_roles = await _approval_roles(db, business_id, approval.risk_level)
    if resolver_role not in allowed_roles:
        raise BusinessRuleError(403, "You do not have permission to decide this approval request")

    approval.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    approval.resolved_by_user_id = resolver_user_id
    approval.resolved_at = utcnow()
    approval.decision_note = decision_note
    await db.flush()

    # If the request targets a PO parked in PENDING_APPROVAL, the decision
    # drives its FR-9 lifecycle: approve -> APPROVED, reject -> CANCELLED.
    if approval.target_type == "purchase_order" and approval.target_id:
        po_result = await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.id == approval.target_id,
                PurchaseOrder.business_id == business_id,
            )
        )
        po = po_result.scalar_one_or_none()
        if po is not None and po.status == PurchaseOrderStatus.PENDING_APPROVAL:
            po.status = (
                PurchaseOrderStatus.APPROVED if approve else PurchaseOrderStatus.CANCELLED
            )

    await record_audit(
        db,
        business_id=business_id,
        actor_type="USER",
        actor_user_id=resolver_user_id,
        action=AuditAction.APPROVAL_DECIDE,
        target_type="approval_request",
        target_id=approval.id,
        summary=f"{'Approved' if approve else 'Rejected'} approval request for {approval.action}",
        after={"status": approval.status.value},
    )
    await db.commit()
    await db.refresh(approval)
    return approval
