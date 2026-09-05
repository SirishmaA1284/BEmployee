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
from app.models.enums import AgentActionStatus, BusinessRole
from app.policies.risk import RiskLevel, classify_action
from app.services.errors import BusinessRuleError
from app.tools.base import ToolError, ToolSpec

_MAX_SUMMARY_CHARS = 600
_MAX_SUMMARY_ITEMS = 25


def _json_safe(value: Any) -> Any:
    """Converts non-JSON values (UUID, Decimal, datetime, enums) to their
    JSON-safe string form so action summaries can always be stored in JSONB.
    """
    if isinstance(value, (uuid.UUID, Decimal, datetime)):
        return str(value)
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump())
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

        risk_level = classify_action(tool, arguments)

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
        return {"ok": True, "data": data}


registry = ToolRegistry()