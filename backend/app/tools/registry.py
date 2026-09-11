"""The tool registry: registration, provider-neutral schemas, and the single
`call` path that validates -> checks permissions -> executes -> records.

Agent code (app/agents) never touches SQLAlchemy; it only calls
`registry.call(...)`. API endpoints never use the registry; they call the
same services directly. That split is structural (ADR-003): the registry is
the only bridge between agent code and data, and it audits every crossing.
"""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.base import ToolCallRequest
from app.models.agent import AgentAction
from app.models.enums import (
    AgentActionStatus,
    AuditAction,
    BusinessRole,
)
from app.policies.policies import evaluate_risk
from app.policies.risk import RiskLevel
from app.services.approval_service import create_approval_request
from app.services.audit_service import record_audit
from app.services.errors import BusinessRuleError
from app.services.purchase_order_service import create_purchase_order as create_po_service
from app.tools.base import ToolError, ToolSpec

_MAX_SUMMARY_CHARS = 600
_MAX_SUMMARY_ITEMS = 25


def _json_safe(value: Any) -> Any:
    """Converts non-JSON values (UUID, Decimal, datetime, enums) to their
    JSON-safe string form so action summaries and approval payloads can
    always be stored in JSONB. Recurses into dicts and lists.
    """
    if isinstance(value, (uuid.UUID, Decimal, datetime)):
        return str(value)
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump())
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    return value


def _compact(value: Any) -> Any:
    """Truncates long strings / big lists in stored action summaries so the
    audit table stays small — a summary, not a dump.
    """
    value = _json_safe(value)
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_compact(v) for v in value[:_MAX_SUMMARY_ITEMS]]
    if isinstance(value, str) and len(value) > _MAX_SUMMARY_CHARS:
        return value[:_MAX_SUMMARY_CHARS] + "…"
    return value


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def schemas(self) -> list[ToolCallRequest]:
        """Provider-neutral schemas (ADR-010) — the only shape the LLM and
        the future MCP server see.
        """
        return [
            ToolCallRequest(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema.model_json_schema(),
            )
            for tool in self._tools.values()
        ]

    async def call(
        self,
        db: AsyncSession,
        *,
        business_id: uuid.UUID,
        role: BusinessRole,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate -> permission-check -> execute -> record. Returns
        {"ok": True, "data": ...} or {"ok": False, "error": ...}; never
        raises into the caller's LLM loop.
        """
        tool = self._tools.get(name)
        if tool is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}

        try:
            validated = tool.input_schema.model_validate(arguments)
        except ValidationError as exc:
            return {
                "ok": False,
                "error": f"Invalid arguments for {name}: {exc.errors(include_url=False)}",
            }

        if tool.required_roles is not None and role not in tool.required_roles:
            return {
                "ok": False,
                "error": f"Tool {name} requires role {'/'.join(r.value for r in tool.required_roles)}",
            }

        risk_level = await evaluate_risk(db, business_id, tool, arguments)

        # HIGH risk always requires human approval (FR-18). Purchase orders
        # follow the FR-9 lifecycle: they are created in PENDING_APPROVAL and
        # an approval request is attached targeting the created PO; other
        # HIGH-risk tools are stopped before execution. Either way there is
        # no code path for an agent to approve its own request.
        if risk_level == RiskLevel.HIGH:
            target_type: str | None = None
            target_id: uuid.UUID | None = None
            data: dict[str, Any] = {}
            if name == "create_purchase_order":
                try:
                    po = await create_po_service(
                        db,
                        business_id=business_id,
                        supplier_id=validated.supplier_id,
                        items=[(i.product_id, i.quantity, i.unit_cost) for i in validated.items],
                        created_by_user_id=user_id,
                        requires_approval=True,
                    )
                except BusinessRuleError as exc:
                    db.add(
                        AgentAction(
                            task_id=task_id,
                            business_id=business_id,
                            tool_name=name,
                            status=AgentActionStatus.FAILED,
                            risk_level=risk_level.value,
                            input_summary=_compact(validated.model_dump()),
                            result_summary={"error": str(exc.detail)},
                            created_by_user_id=user_id,
                        )
                    )
                    return {"ok": False, "error": exc.detail}
                target_type = "purchase_order"
                target_id = po.id
                data = {"purchase_order_id": str(po.id), "status": po.status.value}

            approval = await create_approval_request(
                db,
                business_id=business_id,
                action=name,
                payload=_json_safe(validated.model_dump()),
                risk_level=risk_level.value,
                requested_by_user_id=user_id,
                summary=f"Agent proposed '{name}' with risk {risk_level.value}.",
                target_type=target_type,
                target_id=target_id,
            )
            db.add(
                AgentAction(
                    task_id=task_id,
                    business_id=business_id,
                    tool_name=name,
                    status=AgentActionStatus.PENDING,
                    risk_level=risk_level.value,
                    input_summary=_compact(validated.model_dump()),
                    result_summary=_compact({"needs_approval": True, **data}),
                    created_by_user_id=user_id,
                )
            )
            await db.commit()
            return {
                "ok": False,
                "needs_approval": True,
                "approval_request_id": str(approval.id),
                "data": data,
                "error": (
                    f"This action is high-risk and needs a human approval before it can run. "
                    f"Approval request {str(approval.id)[:8]} was created."
                ),
            }

        try:
            data = await tool.handler(db, business_id, user_id, validated)
            status = AgentActionStatus.SUCCESS
        except (ToolError, BusinessRuleError) as exc:
            status = AgentActionStatus.FAILED
            db.add(
                AgentAction(
                    task_id=task_id,
                    business_id=business_id,
                    tool_name=name,
                    status=status,
                    risk_level=risk_level.value,
                    input_summary=_compact(validated.model_dump()),
                    result_summary={"error": str(exc.detail) if isinstance(exc, BusinessRuleError) else str(exc)},
                    created_by_user_id=user_id,
                )
            )
            return {
                "ok": False,
                "error": exc.detail if isinstance(exc, BusinessRuleError) else str(exc),
            }

        db.add(
            AgentAction(
                task_id=task_id,
                business_id=business_id,
                tool_name=name,
                status=status,
                risk_level=risk_level.value,
                input_summary=_compact(validated.model_dump()),
                result_summary=_compact(json.loads(json.dumps(data, default=str))),
                created_by_user_id=user_id,
            )
        )
        await record_audit(
            db,
            business_id=business_id,
            actor_type="AGENT",
            actor_user_id=user_id,
            action=AuditAction.AGENT_ACTION,
            target_type=name,
            summary=(tool.action_summary or f"Agent executed {name}"),
            after=_compact(data),
        )
        return {"ok": True, "data": data}


registry = ToolRegistry()