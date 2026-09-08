"""Shared agent state (docs/decisions.md ADR-002).

One TypedDict drives every LangGraph workflow in app/agents/workflows and
the orchestrator that routes to them. Extra per-workflow scratch fields are
optional keys; LangGraph merges partial updates from nodes.
"""

import uuid
from typing import Any, TypedDict

from app.models.enums import AgentIntent, BusinessRole


class AgentState(TypedDict, total=False):
    # Identity/context — set by the API layer, never by the LLM.
    business_id: uuid.UUID
    user_id: uuid.UUID
    task_id: uuid.UUID
    role: BusinessRole
    user_message: str

    # Orchestrator classification.
    intent: AgentIntent
    intent_summary: str
    agent_name: str

    # NFR-3: hard cap on LLM calls per request; nodes check it before
    # calling the provider.
    llm_calls: int

    # Extraction results (LLM -> validated Pydantic model dumps).
    extraction: dict[str, Any]

    # Tool results keyed by tool name (last call wins).
    tool_results: dict[str, Any]

    # Order workflow scratch (declared so LangGraph merges node returns).
    customer_id: uuid.UUID
    customer_name: str
    resolved_items: list[dict[str, Any]]
    created_order_id: uuid.UUID

    # Procurement workflow scratch.
    supplier_id: uuid.UUID
    plan_items: list[dict[str, Any]]
    plan_narration: list[str]
    created_po_id: uuid.UUID

    # Approval gating (Phase 5, FR-18): set when a tool call returned
    # `needs_approval` because the policy engine classified the action HIGH.
    # The workflow stops before execution and surfaces the request to the user.
    needs_approval: bool
    approval_request_id: uuid.UUID

    # Output.
    reply: str
    result: dict[str, Any]
    error: str | None
    verified: bool