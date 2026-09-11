"""Approval request lifecycle (FR-18, Phase 9 multi-stage).

- `create_approval_request` is called by the tool registry whenever a HIGH
  risk action is proposed: it records the pending request (and, Phase 9, one
  `ApprovalStep` per required stage) and the registry STOPS before execution.
- `decide` is the human, authenticated decision path. It resolves the
  current PENDING stage: checks the resolver's role against the step's
  APPROVAL_ROLES (copied at creation), and for stage > 1 requires that a
  *different* person than the previous stage's resolver approve it — one
  user cannot rubber-stamp the whole chain. The request only reaches
  APPROVED when every stage is APPROVED; any rejection ends the chain as
  REJECTED. There is no code path for an agent (or the requester) to
  approve their own request.

When an approved request targets a purchase order that was created in
PENDING_APPROVAL, `decide` also transitions that PO to APPROVED (FR-9) once
the final stage approves; a rejection leaves it CANCELLED.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.base import utcnow
from app.models.approval import ApprovalRequest, ApprovalStep
from app.models.enums import ApprovalStatus, AuditAction, PurchaseOrderStatus
from app.models.purchase_order import PurchaseOrder
from app.policies.policies import approval_roles_for, approval_stages_for, get_active_policies
from app.policies.risk import RiskLevel
from app.services.audit_service import record_audit
from app.services.errors import BusinessRuleError


async def _load_with_steps(db: AsyncSession, approval_id: uuid.UUID) -> ApprovalRequest | None:
    result = await db.execute(
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.steps))
        .where(ApprovalRequest.id == approval_id)
    )
    return result.scalar_one_or_none()


def _current_step(approval: ApprovalRequest) -> ApprovalStep | None:
    """The first PENDING stage, or None when every stage is decided."""
    return next((s for s in approval.steps if s.status == ApprovalStatus.PENDING), None)


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
    policies = await get_active_policies(db, business_id)
    required_stages = approval_stages_for(policies)
    roles = approval_roles_for(policies, RiskLevel(risk_level))

    approval = ApprovalRequest(
        business_id=business_id,
        action=action,
        summary=summary,
        payload=payload,
        risk_level=risk_level,
        target_type=target_type,
        target_id=target_id,
        requested_by_user_id=requested_by_user_id,
        required_stages=required_stages,
    )
    db.add(approval)
    await db.flush()
    for stage_number in range(1, required_stages + 1):
        db.add(
            ApprovalStep(
                approval_request_id=approval.id,
                stage_number=stage_number,
                status=ApprovalStatus.PENDING,
                required_roles=roles,
            )
        )
    await db.flush()
    return approval


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
    """Resolves the current PENDING stage of an approval request as a human
    decision. Returns the request (steps loaded) with its updated status."""
    approval = await _load_with_steps(db, approval_id)
    if approval is None or approval.business_id != business_id:
        raise BusinessRuleError(404, "Approval request not found")
    if approval.status != ApprovalStatus.PENDING:
        raise BusinessRuleError(409, f"Approval request is already {approval.status.value}")

    step = _current_step(approval)
    if step is None:
        raise BusinessRuleError(409, "Approval request has no pending stages")

    if resolver_role not in step.required_roles:
        raise BusinessRuleError(403, "You do not have permission to decide this approval request")

    if approve:
        if step.stage_number > 1:
            previous = approval.steps[step.stage_number - 2]
            if previous.resolved_by_user_id == resolver_user_id:
                raise BusinessRuleError(
                    409,
                    "Consecutive approval stages must be decided by different people",
                )
        step.status = ApprovalStatus.APPROVED
        step.resolved_by_user_id = resolver_user_id
        step.resolved_at = utcnow()
        step.decision_note = decision_note

        remaining = _current_step(approval)
        if remaining is not None:
            # More stages to go: the request stays PENDING for the next approver.
            await db.flush()
            await record_audit(
                db,
                business_id=business_id,
                actor_type="USER",
                actor_user_id=resolver_user_id,
                action=AuditAction.APPROVAL_DECIDE,
                target_type="approval_request",
                target_id=approval.id,
                summary=(
                    f"Approved stage {step.stage_number}/{approval.required_stages} "
                    f"of approval request for {approval.action}"
                ),
                after={"status": approval.status.value, "stage": step.stage_number},
            )
            await db.commit()
            await db.refresh(approval)
            return approval

        # Final stage approved: the whole request is APPROVED.
        approval.status = ApprovalStatus.APPROVED
        approval.resolved_by_user_id = resolver_user_id
        approval.resolved_at = utcnow()
        approval.decision_note = decision_note
    else:
        step.status = ApprovalStatus.REJECTED
        step.resolved_by_user_id = resolver_user_id
        step.resolved_at = utcnow()
        step.decision_note = decision_note
        approval.status = ApprovalStatus.REJECTED
        approval.resolved_by_user_id = resolver_user_id
        approval.resolved_at = utcnow()
        approval.decision_note = decision_note

    await db.flush()

    # If the request targets a PO parked in PENDING_APPROVAL, the decision
    # drives its FR-9 lifecycle: full approval -> APPROVED, rejection -> CANCELLED.
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