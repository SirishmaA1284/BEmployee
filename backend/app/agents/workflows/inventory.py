"""Inventory Agent workflows: CHECK_INVENTORY and LOW_STOCK.

Both are fully deterministic after classification — one registry call, no
further LLM involvement (the numbers come from the database, narrated by
template text, never by the model).
"""

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import runner
from app.agents.runner import extract
from app.agents.state import AgentState
from app.core.llm.base import LLMProvider

INVENTORY_EXTRACT_SYSTEM_PROMPT = (
    "Extract which product the user is asking about into `extract_search_query` "
    "(`query`), or an empty query if they ask about everything. Use their own "
    "words; never invent a product."
)


class SearchQueryExtraction(BaseModel):
    query: str = Field(default="", max_length=200)


def _low_stock_line(item: dict[str, Any]) -> str:
    return (
        f"{item['product_name']} ({item['sku']}) — {item['quantity_on_hand']} on hand, "
        f"threshold {item['reorder_threshold']}"
    )


def build_low_stock_workflow(provider: LLMProvider, db: AsyncSession):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def check_node(state: AgentState) -> dict[str, Any]:
        result = await runner.run_tool(state, db, "list_low_stock", {})
        if not result.get("ok"):
            return {"error": f"Could not check stock: {result.get('error')}"}
        items = result["data"].get("items", [])
        return {
            "reply": (
                "No products are running low — stock is healthy."
                if not items
                else f"{len(items)} product(s) at or below reorder threshold: "
                + "; ".join(_low_stock_line(item) for item in items)
                + ". Want me to prepare a purchase order for these?"
            ),
            "result": {"low_stock": items},
        }

    graph.add_node("check", check_node)
    graph.add_edge(START, "check")
    graph.add_edge("check", END)
    return graph.compile()


def build_check_inventory_workflow(provider: LLMProvider, db: AsyncSession):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def extract_node(state: AgentState) -> dict[str, Any]:
        updates, extraction = await extract(
            provider,
            state,
            tool_name="extract_search_query",
            tool_description="Extract which product the user asked about.",
            schema=SearchQueryExtraction,
            system_prompt=INVENTORY_EXTRACT_SYSTEM_PROMPT,
        )
        if extraction is None:
            return updates
        return {**updates, "extraction": extraction.model_dump()}

    async def check_node(state: AgentState) -> dict[str, Any]:
        query = state.get("extraction", {}).get("query", "")
        result = await runner.run_tool(state, db, "check_stock", {"search": query or None})
        if not result.get("ok"):
            return {"error": f"Could not check stock: {result.get('error')}"}
        items = result["data"].get("items", [])
        if not items:
            return {"reply": f"No stock found{(' for ' + query) if query else ''}.", "result": {"items": []}}
        return {
            "reply": (
                f"{len(items)} item(s) in inventory{(' for ' + query) if query else ''}: "
                + "; ".join(_low_stock_line(item) for item in items)
            ),
            "result": {"items": items},
        }

    graph.add_node("extract", extract_node)
    graph.add_node("check", check_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "check")
    graph.add_edge("check", END)
    return graph.compile()