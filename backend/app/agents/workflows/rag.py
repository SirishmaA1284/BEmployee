"""RAG Agent workflow: ASK_DOCUMENTS (Phase 7, FR-21/22/23).

Retrieves business-scoped document chunks for the user's question, grounds
the LLM answer on them (wrapped as untrusted data — docs/architecture.md §4),
and reports the cited sources. Deterministic retrieval; only the grounding
answer call uses the LLM.
"""

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import runner
from app.agents.runner import extract
from app.agents.state import AgentState
from app.core.llm.base import LLMProvider
from app.rag.answer import answer_query

RAG_EXTRACT_SYSTEM_PROMPT = (
    "Extract the user's question about their business documents into "
    "`extract_document_query` (`query`). Keep their words; never invent one."
)


class DocumentQueryExtraction(BaseModel):
    query: str = Field(min_length=1, max_length=500)


def build_rag_workflow(provider: LLMProvider, db: AsyncSession):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def extract_node(state: AgentState) -> dict[str, Any]:
        updates, extraction = await extract(
            provider,
            state,
            tool_name="extract_document_query",
            tool_description="Extract the question to ask about the business's documents.",
            schema=DocumentQueryExtraction,
            system_prompt=RAG_EXTRACT_SYSTEM_PROMPT,
        )
        if extraction is None:
            return updates
        return {**updates, "extraction": extraction.model_dump()}

    async def answer_node(state: AgentState) -> dict[str, Any]:
        query = state.get("extraction", {}).get("query", "").strip()
        if not query:
            return {
                "reply": "I couldn't tell what you'd like to know from your documents. "
                "Try asking a specific question, e.g. \"What does our return policy say?\"",
                "error": "empty query",
            }
        result = await answer_query(
            db,
            state["business_id"],
            query,
            llm=provider,
        )
        if result["chunks_used"] == 0:
            return {
                "reply": result["answer"],
                "result": {"sources": [], "chunks_used": 0},
            }
        source_names = " | ".join(s["document_name"] for s in result["sources"])
        reply = (
            f"{result['answer']}\n\nSources: {source_names}"
        )
        return {
            "reply": reply,
            "result": {"sources": result["sources"], "chunks_used": result["chunks_used"]},
        }

    graph.add_node("extract", extract_node)
    graph.add_node("answer", answer_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "answer")
    graph.add_edge("answer", END)
    return graph.compile()