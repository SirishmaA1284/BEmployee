"""Order Agent workflow (docs/architecture.md §2).

EXTRACT (LLM) -> resolve customer/products (registry tools) ->
create_order (registry tool -> deterministic service) -> verify (Verification
Agent) -> summarize.

The LLM only extracts and narrates; stock math, totals and the transaction
all live in app/services/order_service.py (Rule 4).
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import runner
from app.agents.intents import CLASSIFY_SYSTEM_PROMPT
from app.agents.runner import extract
from app.agents.state import AgentState
from app.agents.verification import verify_created_order
from app.core.llm.base import LLMProvider


class OrderItemExtraction(BaseModel):
    product_query: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0)


class OrderExtraction(BaseModel):
    customer_query: str = Field(min_length=1, max_length=200)
    items: list[OrderItemExtraction] = Field(min_length=1)


ORDER_EXTRACT_SYSTEM_PROMPT = (
    CLASSIFY_SYSTEM_PROMPT.split("Intents:")[0]
    + "Extract the order request into `extract_order` arguments: the customer "
    "name (`customer_query`) and each line item as `product_query` (the product "
    "name or SKU the user said) with its `quantity`. Never invent products or "
    "quantities that are not in the message; if anything is missing or "
    "ambiguous, omit it so the workflow can ask."
)


def build_order_workflow(provider: LLMProvider, db: AsyncSession):
    """Per-request compiled graph: nodes close over this request's provider
    and database session (LangGraph state stays plain/JSON-serializable).
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def extract_node(state: AgentState) -> dict[str, Any]:
        updates, extraction = await extract(
            provider,
            state,
            tool_name="extract_order",
            tool_description="Extract customer and line items from an order request.",
            schema=OrderExtraction,
            system_prompt=ORDER_EXTRACT_SYSTEM_PROMPT,
        )
        if extraction is None:
            if updates.get("error"):
                return {**updates, "reply": f"Sorry — {updates['error']}"}
            return {
                **updates,
                "reply": "I couldn't parse your order request. Try: "
                '"Create an order for Rahul with 3 coffee packets and 2 sugar bags."',
            }
        return {**updates, "extraction": extraction.model_dump()}

    async def resolve_node(state: AgentState) -> dict[str, Any]:
        """Maps extracted names to real ids via registry tools. Never guesses
        — only registry results are used.
        """
        if state.get("error") or not state.get("extraction"):
            return {}
        extraction = state["extraction"]

        customer_result = await runner.run_tool(
            state, db, "search_customers", {"query": extraction["customer_query"]}
        )
        if not customer_result.get("ok"):
            return {"error": f"Could not search customers: {customer_result.get('error')}"}
        customers = customer_result["data"].get("customers", [])
        if not customers:
            return {
                "error": f"No customer matches '{extraction['customer_query']}'. "
                "Add the customer first, then retry."
            }
        customer = customers[0]
        customer_id = uuid.UUID(str(customer["customer_id"]))

        resolved_items: list[dict[str, Any]] = []
        for line in extraction["items"]:
            product_result = await runner.run_tool(
                state, db, "search_products", {"query": line["product_query"]}
            )
            if not product_result.get("ok"):
                return {"error": f"Could not search products: {product_result.get('error')}"}
            products = product_result["data"].get("products", [])
            if not products:
                return {"error": f"No product matches '{line['product_query']}'."}
            product = next((p for p in products if p.get("is_active")), products[0])
            resolved_items.append(
                {"product_id": product["product_id"], "quantity": line["quantity"]}
            )

        return {"customer_id": customer_id, "customer_name": customer["name"], "resolved_items": resolved_items}

    async def create_node(state: AgentState) -> dict[str, Any]:
        if state.get("error") or not state.get("customer_id"):
            return {}
        result = await runner.run_tool(
            state,
            db,
            "create_order",
            {"customer_id": str(state["customer_id"]), "items": state["resolved_items"]},
        )
        if result.get("needs_approval"):
            return {
                "needs_approval": True,
                "approval_request_id": result.get("approval_request_id"),
                "reply": (
                    f"This order is high-risk and needs a human approval before it can run. "
                    f"An approval request ({result.get('approval_request_id', '')[:8]}) was created "
                    "for a manager to review."
                ),
                "result": {"needs_approval": True, "approval_request_id": result.get("approval_request_id")},
            }
        if not result.get("ok"):
            return {"error": f"Order could not be created: {result.get('error')}"}
        return {"created_order_id": result["data"]["order_id"]}

    async def verify_node(state: AgentState) -> dict[str, Any]:
        if state.get("error") or not state.get("created_order_id"):
            return {}
        problems = await verify_created_order(state, db)
        return {"verified": not problems, **({"error": problems} if problems else {})}

    async def summarize_node(state: AgentState) -> dict[str, Any]:
        if state.get("reply"):
            return {}
        if state.get("error"):
            return {"reply": f"Sorry — I couldn't complete the order: {state['error']}"}
        if not state.get("verified"):
            return {
                "reply": "Sorry — the order was created but verification failed, so I can't "
                "confirm it. Please check recent orders."
            }
        order = state["tool_results"]["get_order"]["data"]
        lines = ", ".join(
            f"{item['quantity']} x {item['name']} ({item['line_total']} {order['currency']})"
            for item in order["items"]
        )
        return {
            "reply": (
                f"Order {order['order_id'][:8]} created for {state['customer_name']} — "
                f"total {order['total']} {order['currency']} ({lines}). "
                f"Invoice {order['invoice_number']} was generated and stock was updated. Verified."
            ),
            "result": order,
        }

    graph.add_node("extract", extract_node)
    graph.add_node("resolve", resolve_node)
    graph.add_node("create", create_node)
    graph.add_node("verify", verify_node)
    graph.add_node("summarize", summarize_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "resolve")
    graph.add_edge("resolve", "create")
    graph.add_edge("create", "verify")
    graph.add_edge("verify", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()