"""Customer Agent (SEARCH_CUSTOMERS) and catalog lookup (SEARCH_PRODUCTS)
workflows — simple extract -> search -> narrate, registry-only data access.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import runner
from app.agents.runner import extract
from app.agents.state import AgentState
from app.agents.workflows.inventory import SearchQueryExtraction
from app.core.llm.base import LLMProvider

SEARCH_SYSTEM_PROMPT = (
    "Extract the thing the user wants to look up into `extract_search_query` "
    "(`query`). Use their own words; never invent a name."
)


def _build_search_workflow(provider: LLMProvider, db: AsyncSession, tool_name: str):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def extract_node(state: AgentState) -> dict[str, Any]:
        updates, extraction = await extract(
            provider,
            state,
            tool_name="extract_search_query",
            tool_description="Extract the search term from the request.",
            schema=SearchQueryExtraction,
            system_prompt=SEARCH_SYSTEM_PROMPT,
        )
        if extraction is None:
            return updates
        return {**updates, "extraction": extraction.model_dump()}

    async def search_node(state: AgentState) -> dict[str, Any]:
        query = state.get("extraction", {}).get("query", "")
        result = await runner.run_tool(state, db, tool_name, {"query": query})
        if not result.get("ok"):
            return {"error": f"Could not search: {result.get('error')}"}
        data = result["data"]
        return {"result": data, "reply": _narrate(tool_name, data, query)}

    graph.add_node("extract", extract_node)
    graph.add_node("search", search_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "search")
    graph.add_edge("search", END)
    return graph.compile()


def _narrate(tool_name: str, data: dict[str, Any], query: str) -> str:
    if tool_name == "search_products":
        products = data.get("products", [])
        if not products:
            return f"No products match '{query}'."
        lines = "; ".join(
            f"{p['name']} ({p['sku']}) at {p['unit_price']}" for p in products
        )
        return f"{len(products)} product(s) matching '{query}': {lines}"
    customers = data.get("customers", [])
    if not customers:
        return f"No customers match '{query}'."
    lines = "; ".join(f"{c['name']} ({c['email'] or 'no email'})" for c in customers)
    return f"{len(customers)} customer(s) matching '{query}': {lines}"


def build_search_products_workflow(provider: LLMProvider, db: AsyncSession):
    return _build_search_workflow(provider, db, "search_products")


def build_search_customers_workflow(provider: LLMProvider, db: AsyncSession):
    return _build_search_workflow(provider, db, "search_customers")