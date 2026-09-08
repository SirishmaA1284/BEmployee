"""AI Employee chat API (FR-11).

POST /api/agent/chat runs one full agent cycle synchronously: classify ->
route -> workflow -> verify -> summarize, persisting an AgentSession, an
AgentTask per request and an AgentAction per tool call (FR-14/FR-15). The
response carries the natural-language reply plus structured `result` data
the frontend can render (order summary, low-stock table, rankings, ...).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_agent
from app.core.llm.base import LLMProvider
from app.core.llm.providers import get_llm_provider
from app.core.logging import get_logger, log_agent_run
from app.database.base import utcnow
from app.database.session import get_db
from app.models.agent import AgentAction, AgentSession, AgentTask
from app.models.business_member import BusinessMember
from app.models.enums import AgentSessionStatus, AgentTaskStatus, AgentIntent
from app.models.user import User
from app.schemas.agent import (
    AgentActionRead,
    AgentSessionDetail,
    AgentSessionSummary,
    AgentTaskRead,
    ChatRequest,
    ChatResponse,
)
from app.security.dependencies import get_current_membership, get_current_user
from app.security.rate_limit import rate_limit

router = APIRouter(prefix="/api/agent", tags=["agent"])

_logger = get_logger("agent")


async def _resolve_provider() -> LLMProvider:
    return get_llm_provider()


def _session_status(state: dict) -> AgentSessionStatus:
    if state.get("intent") == AgentIntent.UNKNOWN:
        return AgentSessionStatus.NEEDS_CLARIFICATION
    if state.get("error"):
        return AgentSessionStatus.FAILED
    return AgentSessionStatus.COMPLETED


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    membership: BusinessMember = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    provider: LLMProvider = Depends(_resolve_provider),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit(limit=20, window_seconds=60)),
) -> ChatResponse:
    session = AgentSession(
        business_id=membership.business_id,
        user_id=current_user.id,
        status=AgentSessionStatus.RUNNING,
        user_message=payload.message,
    )
    db.add(session)
    await db.flush()

    task = AgentTask(session_id=session.id, status=AgentTaskStatus.RUNNING)
    db.add(task)
    await db.flush()

    final_state = await run_agent(
        provider,
        db,
        business_id=membership.business_id,
        user_id=current_user.id,
        role=membership.role,
        task_id=task.id,
        message=payload.message,
    )

    status_value = _session_status(final_state)
    log_agent_run(
        _logger,
        logging.INFO,
        "agent run finished",
        request_id=getattr(request.state, "request_id", None),
        session_id=session.id,
        task_id=task.id,
        intent=final_state.get("intent"),
        agent_name=final_state.get("agent_name"),
        status=status_value.value,
    )

    session.intent = final_state.get("intent")
    session.status = status_value
    session.reply = final_state.get("reply")
    if status_value != AgentSessionStatus.RUNNING:
        session.completed_at = utcnow()

    task.agent_name = final_state.get("agent_name")
    task.status = (
        AgentTaskStatus.COMPLETED if status_value == AgentSessionStatus.COMPLETED else AgentTaskStatus.FAILED
    )
    task.completed_at = utcnow()

    await db.commit()
    await db.refresh(session)

    return ChatResponse(
        session_id=session.id,
        intent=final_state.get("intent", AgentIntent.UNKNOWN),
        agent_name=final_state.get("agent_name", "orchestrator"),
        status=status_value,
        reply=session.reply or "",
        result=final_state.get("result"),
    )


async def _session_summary(db: AsyncSession, session: AgentSession) -> AgentSessionSummary:
    task_result = await db.execute(
        select(AgentTask).where(AgentTask.session_id == session.id).order_by(AgentTask.started_at)
    )
    task = task_result.scalars().first()
    return AgentSessionSummary(
        id=session.id,
        intent=session.intent,
        agent_name=task.agent_name if task else None,
        status=session.status,
        user_message=session.user_message,
        reply=session.reply,
        created_at=session.created_at,
    )


@router.get("/sessions", response_model=list[AgentSessionSummary])
async def list_sessions(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[AgentSessionSummary]:
    result = await db.execute(
        select(AgentSession)
        .where(
            AgentSession.business_id == membership.business_id,
            AgentSession.user_id == membership.user_id,
        )
        .order_by(AgentSession.created_at.desc())
        .limit(50)
    )
    return [await _session_summary(db, s) for s in result.scalars().all()]


@router.get("/sessions/{session_id}", response_model=AgentSessionDetail)
async def get_session(
    session_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> AgentSessionDetail:
    result = await db.execute(
        select(AgentSession).where(
            AgentSession.id == session_id, AgentSession.business_id == membership.business_id
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    tasks_result = await db.execute(
        select(AgentTask).where(AgentTask.session_id == session.id).order_by(AgentTask.started_at)
    )
    tasks = []
    for task in tasks_result.scalars().all():
        actions_result = await db.execute(
            select(AgentAction).where(AgentAction.task_id == task.id).order_by(AgentAction.created_at)
        )
        tasks.append(
            AgentTaskRead(
                id=task.id,
                agent_name=task.agent_name,
                status=task.status,
                started_at=task.started_at,
                completed_at=task.completed_at,
                actions=[
                    AgentActionRead(
                        id=action.id,
                        tool_name=action.tool_name,
                        status=action.status,
                        risk_level=action.risk_level,
                        input_summary=action.input_summary,
                        result_summary=action.result_summary,
                        created_at=action.created_at,
                    )
                    for action in actions_result.scalars().all()
                ],
            )
        )

    return AgentSessionDetail(
        id=session.id,
        intent=session.intent,
        status=session.status,
        user_message=session.user_message,
        reply=session.reply,
        created_at=session.created_at,
        completed_at=session.completed_at,
        tasks=tasks,
    )