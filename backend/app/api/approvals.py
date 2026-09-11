"""Approval request API (FR-18, Phase 9 multi-stage).

HIGH-risk actions (or policy-flagged writes) create an approval request and
stop before execution. A human resolves the current stage here; the decision
is role-gated by the step's APPROVAL_ROLES (copied from the business policy
at request creation, default OWNER/ADMIN), and consecutive stages must be
decided by different people. There is no code path for an agent to approve
its own request.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.approval import ApprovalRequest
from app.models.business_member import BusinessMember
from app.models.enums import ApprovalStatus
from app.models.user import User
from app.schemas.approval import ApprovalDecision, ApprovalRequestRead, ApprovalStepRead
from app.security.dependencies import get_current_membership, get_current_user
from app.services.approval_service import decide
from app.services.errors import BusinessRuleError

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _to_read(approval: ApprovalRequest) -> ApprovalRequestRead:
    steps = list(approval.steps)
    current_stage = next(
        (s.stage_number for s in steps if s.status == ApprovalStatus.PENDING),
        approval.required_stages,
    )
    return ApprovalRequestRead(
        id=approval.id,
        action=approval.action,
        summary=approval.summary,
        payload=approval.payload,
        risk_level=approval.risk_level,
        target_type=approval.target_type,
        target_id=approval.target_id,
        status=approval.status,
        requested_by_user_id=approval.requested_by_user_id,
        resolved_by_user_id=approval.resolved_by_user_id,
        resolved_at=approval.resolved_at,
        decision_note=approval.decision_note,
        created_at=approval.created_at,
        required_stages=approval.required_stages,
        current_stage=current_stage,
        steps=[
            ApprovalStepRead(
                id=s.id,
                stage_number=s.stage_number,
                status=s.status,
                required_roles=s.required_roles,
                resolved_by_user_id=s.resolved_by_user_id,
                resolved_at=s.resolved_at,
                decision_note=s.decision_note,
                created_at=s.created_at,
            )
            for s in steps
        ],
    )


@router.get("", response_model=list[ApprovalRequestRead])
async def list_approval_requests(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    status_filter: ApprovalStatus | None = None,
) -> list[ApprovalRequestRead]:
    statement = (
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.steps))
        .where(ApprovalRequest.business_id == membership.business_id)
    )
    if status_filter is not None:
        statement = statement.where(ApprovalRequest.status == status_filter)
    statement = statement.order_by(ApprovalRequest.created_at.desc()).limit(100)
    result = await db.execute(statement)
    return [_to_read(a) for a in result.scalars().all()]


@router.get("/{approval_id}", response_model=ApprovalRequestRead)
async def get_approval_request(
    approval_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestRead:
    result = await db.execute(
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.steps))
        .where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.business_id == membership.business_id,
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return _to_read(approval)


async def _decide(
    approval_id: uuid.UUID,
    approve: bool,
    payload: ApprovalDecision,
    membership: BusinessMember,
    current_user: User,
    db: AsyncSession,
) -> ApprovalRequestRead:
    try:
        approval = await decide(
            db,
            approval_id=approval_id,
            business_id=membership.business_id,
            resolver_user_id=current_user.id,
            resolver_role=membership.role.value,
            approve=approve,
            decision_note=payload.decision_note,
        )
    except BusinessRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _to_read(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalRequestRead)
async def approve_request(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    membership: BusinessMember = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestRead:
    return await _decide(approval_id, True, payload, membership, current_user, db)


@router.post("/{approval_id}/reject", response_model=ApprovalRequestRead)
async def reject_request(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    membership: BusinessMember = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestRead:
    return await _decide(approval_id, False, payload, membership, current_user, db)