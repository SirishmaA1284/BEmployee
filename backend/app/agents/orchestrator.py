"""Orchestrator Agent (docs/architecture.md §1/§2, ADR-002).

One StateGraph per chat request: a `classify` node (structured LLM call)
routes to the right workflow subgraph via conditional edges — control flow
is an explicit graph, not free-form LLM improvisation. The Policy Agent
(risk classification) is applied structurally by the tool registry on every
call (docs/policies); its full policy engine lands in Phase 5.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.intents import CLASSIFY_SYSTEM_PROMPT, CLASSIFY_TOOL, IntentClassification
from app.agents.runner import extract
from app.agents.state import AgentState
from app.agents.workflows.customer import build_search_customers_workflow, build_search_products_workflow
from app.agents.workflows.finance import build_sales_report_workflow
from app.agents.workflows.inventory import build_check_inventory_workflow, build_low_stock_workflow
from app.agents.workflows.order import build_order_workflow
from app.agents.workflows.procurement import build_compare_suppliers_workflow, build_create_purchase_order_workflow
from app.core.llm.base import LLMProvider
from app.models.enums import AgentIntent

CLARIFY_REPLY = (
    "I couldn't work out what you'd like me to do. I can help with: "
    "placing orders (\"Create an order for Rahul with 3 coffee\"), checking "
    "stock (\"Which products are running low?\"), comparing suppliers "
    "(\"Best price for coffee?\"), preparing purchase orders, and sales reports."
)

_INTENT_AGENT = {
    AgentIntent.CREATE_ORDER: "order",
    AgentIntent.CHECK_INVENTORY: "inventory",
    AgentIntent.LOW_STOCK: "inventory",
    AgentIntent.COMPARE_SUPPLIERS: "procurement",
    AgentIntent.CREATE_PURCHASE_ORDER: "procurement",
    AgentIntent.SEARCH_PRODUCTS: "customer",
    AgentIntent.SEARCH_CUSTOMERS: "customer",
    AgentIntent.SALES_REPORT: "finance",
}


_ROUTED_INTENTS = {
    AgentIntent.CREATE_ORDER,
    AgentIntent.CHECK_INVENTORY,
    AgentIntent.LOW_STOCK,
    AgentIntent.COMPARE_SUPPLIERS,
    AgentIntent.CREATE_PURCHASE_ORDER,
    AgentIntent.SEARCH_PRODUCTS,
    AgentIntent.SEARCH_CUSTOMERS,
    AgentIntent.SALES_REPORT,
}


def _workflow_for(intent: AgentIntent, provider: LLMProvider, db: AsyncSession):
    if intent == AgentIntent.CREATE_ORDER:
        return build_order_workflow(provider, db)
    if intent == AgentIntent.LOW_STOCK:
        return build_low_stock_workflow(provider, db)
    if intent == AgentIntent.CHECK_INVENTORY:
        return build_check_inventory_workflow(provider, db)
    if intent == AgentIntent.COMPARE_SUPPLIERS:
        return build_compare_suppliers_workflow(provider, db)
    if intent == AgentIntent.CREATE_PURCHASE_ORDER:
        return build_create_purchase_order_workflow(provider, db)
    if intent == AgentIntent.SEARCH_PRODUCTS:
        return build_search_products_workflow(provider, db)
    if intent == AgentIntent.SEARCH_CUSTOMERS:
        return build_search_customers_workflow(provider, db)
    if intent == AgentIntent.SALES_REPORT:
        return build_sales_report_workflow(provider, db)
    return None


def build_orchestrator(provider: LLMProvider, db: AsyncSession):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def classify_node(state: AgentState) -> dict[str, Any]:
        updates, classification = await extract(
            provider,
            state,
            tool_name=CLASSIFY_TOOL.name,
            tool_description=CLASSIFY_TOOL.description,
            schema=IntentClassification,
            system_prompt=CLASSIFY_SYSTEM_PROMPT,
        )
        if classification is None:
            if updates.get("error"):
                return {**updates, "intent": AgentIntent.UNKNOWN, "reply": f"Sorry — {updates['error']}"}
            return {**updates, "intent": AgentIntent.UNKNOWN, "reply": CLARIFY_REPLY}
        intent = classification.intent
        return {
            **updates,
            "intent": intent,
            "intent_summary": classification.summary,
            "agent_name": _INTENT_AGENT.get(intent, "orchestrator"),
        }

    def route(state: AgentState) -> str:
        intent = state.get("intent", AgentIntent.UNKNOWN)
        if intent not in _ROUTED_INTENTS:
            return "clarify"
        return intent.value

    async def clarify_node(state: AgentState) -> dict[str, Any]:
        # Respect an existing reply (e.g. a step-limit or classification
        # error already produced one) — never clobber it with the generic
        # help text.
        if state.get("reply"):
            return {}
        return {"reply": CLARIFY_REPLY, "result": {"clarified": False}}

    graph.add_node("classify", classify_node)
    graph.add_node("clarify", clarify_node)

    for intent in _ROUTED_INTENTS:
        graph.add_node(intent.value, _workflow_for(intent, provider, db))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify", route, {intent.value: intent.value for intent in _ROUTED_INTENTS} | {"clarify": "clarify"}
    )
    graph.add_edge("clarify", END)
    for intent in _ROUTED_INTENTS:
        graph.add_edge(intent.value, END)
    return graph.compile()


async def run_agent(
    provider: LLMProvider,
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    role: Any,
    task_id: uuid.UUID,
    message: str,
) -> AgentState:
    """Runs the orchestrator for one chat request and returns the final state."""
    orchestrator = build_orchestrator(provider, db)
    final = await orchestrator.ainvoke(
        {
            "business_id": business_id,
            "user_id": user_id,
            "role": role,
            "task_id": task_id,
            "user_message": message,
            "intent": AgentIntent.UNKNOWN,
            "agent_name": "orchestrator",
            "llm_calls": 0,
            "tool_results": {},
        }
    )
    if not final.get("reply"):
        final["reply"] = final.get("error") or "Something went wrong while processing your request."
    return final