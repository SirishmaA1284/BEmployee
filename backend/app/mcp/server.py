"""Minimal read-only MCP server (Phase 7, docs/decisions.md ADR-010, A7).

Exposes a deliberately small, read-only subset of the internal tool registry
over MCP's JSON-RPC 2.0 protocol (`tools/list`, `tools/call`). Uses the same
server-side authorization as the REST API: a JWT `Authorization` header +
`X-Business-Id` header, role resolved from `business_members`. There is no
write path here by design (ADR-010) — external clients can only ask
questions, never mutate data.

HTTP transport with JSON-RPC (POST /mcp):
  {"jsonrpc":"2.0","method":"tools/list","id":1}
  {"jsonrpc":"2.0","method":"tools/call",
   "params":{"name":"get_sales_report","arguments":{}},"id":2}

Tool schemas are reused verbatim from app/tools/registry (already
provider-neutral, ADR-010). Calls run through the registry so validation,
role checks, and the audit trail all still apply (ADR-003); each MCP call
gets its own agent_session/task so the recorded AgentAction has a valid FK.
"""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import utcnow
from app.database.session import get_db
from app.models.agent import AgentSession, AgentTask
from app.models.business_member import BusinessMember
from app.models.enums import AgentSessionStatus, AgentTaskStatus
from app.security.jwt import TokenError, decode_access_token
from app.tools.registry import registry

router = APIRouter(prefix="/mcp", tags=["mcp"])

# The deliberately small read-only subset (ADR-010). No write tools.
_READ_ONLY_TOOLS = {
    "get_sales_report",
    "search_products",
    "check_stock",
    "list_low_stock",
    "compare_supplier_prices",
    "list_orders",
    "list_purchase_orders",
}


async def _resolve_membership(
    authorization: str | None = Header(default=None),
    x_business_id: uuid.UUID | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> tuple[uuid.UUID, Any, uuid.UUID]:
    """Resolve (business_id, role, user_id) exactly like the REST API: JWT
    identity + server-side business_members lookup — never client-asserted.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except TokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if not x_business_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Business-Id header")

    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.business_id == x_business_id,
            BusinessMember.user_id == uuid.UUID(user_id),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this business")
    return membership.business_id, membership.role, membership.user_id


def _error(id: Any, message: str, code: int = -32601) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _result(id: Any, data: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": data}


@router.post("")
async def mcp_endpoint(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_business_id: uuid.UUID | None = Header(default=None),
) -> dict[str, Any]:
    """Single JSON-RPC 2.0 endpoint: tools/list and tools/call."""
    method = payload.get("method")
    rpc_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return _error(rpc_id, "Invalid JSON-RPC version", -32600)

    business_id, role, user_id = await _resolve_membership(authorization, x_business_id, db)

    if method == "tools/list":
        schemas = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema.model_json_schema(),
            }
            for tool in registry.all()
            if tool.name in _READ_ONLY_TOOLS
        ]
        return _result(rpc_id, {"tools": schemas})

    if method == "tools/call":
        params = payload.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in _READ_ONLY_TOOLS:
            return _error(rpc_id, f"Tool '{name}' is not exposed by the MCP server", -32601)
        tool = registry.get(name)
        if tool is None:
            return _error(rpc_id, f"Unknown tool: {name}", -32602)

        # Registry calls record an AgentAction which requires a valid task FK.
        # Create a session+task for this MCP call so the audit trail stays
        # intact (same pattern as the chat API).
        session = AgentSession(
            business_id=business_id,
            user_id=user_id,
            status=AgentSessionStatus.COMPLETED,
            user_message=f"MCP call: {name}",
        )
        db.add(session)
        await db.flush()
        task = AgentTask(session_id=session.id, agent_name="mcp", status=AgentTaskStatus.RUNNING)
        db.add(task)
        await db.flush()

        call = await registry.call(
            db,
            business_id=business_id,
            role=role,
            task_id=task.id,
            user_id=user_id,
            name=name,
            arguments=arguments,
        )
        task.status = AgentTaskStatus.COMPLETED
        task.completed_at = utcnow()
        session.reply = "MCP tool call completed"
        session.completed_at = utcnow()
        await db.commit()
        return _result(rpc_id, call)

    return _error(rpc_id, f"Method not found: {method}", -32601)