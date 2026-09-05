"""Shared helpers for agent nodes: bounded LLM extraction and registry tool
execution. Node code is deliberately thin — the actual work happens in the
registry (which validates, permission-checks and audits) and the services
(which own deterministic business logic).

LangGraph node rule: nodes receive a (shallow) copy of state; top-level
mutations are lost, only the returned dict merges. Helpers therefore return
the partial-state updates they produce instead of mutating `state`.
"""

import uuid
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.llm.base import LLMProvider, ToolCallRequest
from app.tools.registry import registry

T = TypeVar("T", bound=BaseModel)


async def run_tool(
    state: AgentState, db: AsyncSession, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Registry-only tool execution. The result is recorded into the shared
    `tool_results` mapping (nested object — visible to later nodes and the
    final state) and also returned for the caller's immediate use.
    """
    result = await registry.call(
        db,
        business_id=state["business_id"],
        role=state["role"],
        task_id=state["task_id"],
        user_id=state["user_id"],
        name=name,
        arguments=arguments,
    )
    state.setdefault("tool_results", {})[name] = result
    return result


async def extract(
    provider: LLMProvider,
    state: AgentState,
    *,
    tool_name: str,
    tool_description: str,
    schema: type[T],
    system_prompt: str,
) -> tuple[dict[str, Any], T | None]:
    """One bounded structured extraction: the provider must call exactly the
    named tool; its arguments are validated against `schema` before use.

    Returns (state_updates, extraction). On guard trips or bad output the
    updates carry the `error` and `llm_calls` the node must merge.
    """
    settings = get_settings()
    llm_calls = state.get("llm_calls", 0) + 1
    if llm_calls > settings.max_agent_steps:
        return (
            {"llm_calls": llm_calls, "error": f"Exceeded max agent steps ({settings.max_agent_steps})"},
            None,
        )

    response = await provider.generate(
        system=system_prompt,
        messages=[{"role": "user", "content": state["user_message"]}],
        tools=[ToolCallRequest(name=tool_name, description=tool_description, input_schema=schema.model_json_schema())],
    )
    if not response.tool_calls:
        return ({"llm_calls": llm_calls, "error": "The model did not return a structured extraction."}, None)

    call = response.tool_calls[0]
    if call.name != tool_name:
        return ({"llm_calls": llm_calls, "error": f"Model called unexpected tool '{call.name}'."}, None)
    try:
        return ({"llm_calls": llm_calls}, schema.model_validate(call.arguments))
    except Exception:
        return ({"llm_calls": llm_calls, "error": f"Model returned invalid arguments for {tool_name}."}, None)