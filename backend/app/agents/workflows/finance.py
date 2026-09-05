"""Finance/Reporting Agent workflow (SALES_REPORT).

The numbers are computed by app/services/reporting.py (deterministic SQL
aggregation); the LLM is not involved beyond intent classification.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import runner
from app.agents.state import AgentState


def build_sales_report_workflow(provider, db: AsyncSession):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def report_node(state: AgentState) -> dict[str, Any]:
        result = await runner.run_tool(state, db, "get_sales_report", {})
        if not result.get("ok"):
            return {"error": f"Could not build the report: {result.get('error')}"}
        data = result["data"]
        return {
            "reply": (
                f"Sales summary: {data['order_count']} order(s), gross sales "
                f"{data['gross_sales']}, invoiced {data['invoiced_total']}, "
                f"collected {data['collected']}, outstanding {data['outstanding']}."
            ),
            "result": data,
        }

    graph.add_node("report", report_node)
    graph.add_edge(START, "report")
    graph.add_edge("report", END)
    return graph.compile()