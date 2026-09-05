"""Tool contract (docs/decisions.md ADR-003, docs/tools.md).

A ToolSpec is a named, schema-validated, permissioned callable — the only
thing agent code may use to touch business data. Rules enforced here (and
only here):

- arguments are re-validated against the Pydantic input schema no matter
  what the LLM claims;
- the caller's role is checked against `required_roles` server-side;
- every execution is persisted as an AgentAction (FR-14) with a concise
  summary — never raw chain-of-thought — and its deterministic risk level
  (docs/decisions.md ADR-004);
- errors are returned as structured results, never raised into the LLM loop.

Handlers receive (db, business_id, user_id, validated_args) and return a
JSON-serializable dict.
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from app.models.enums import BusinessRole
from app.policies.risk import RiskLevel


class ToolError(Exception):
    """Raised by the registry for anything that prevents execution
    (unknown tool, invalid arguments, missing permission, business rule
    rejection). Converted to a structured error result by `ToolRegistry.call`.
    """


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: type[BaseModel]
    risk_level: RiskLevel
    handler: Callable[[Any, Any, Any, BaseModel], Awaitable[dict[str, Any]]]
    # None = any member of the business may call this tool. Role is always
    # the server-resolved one from business_members, never client-asserted.
    required_roles: tuple[BusinessRole, ...] | None = None
    # What the tool changes, in one line, for the human-facing activity log.
    action_summary: str = field(default="")