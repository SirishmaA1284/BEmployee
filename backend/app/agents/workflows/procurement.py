"""Procurement Agent workflows: COMPARE_SUPPLIERS and CREATE_PURCHASE_ORDER.

Supplier ranking is the deterministic function from app/services/procurement.py
(the same one the REST `/compare` endpoint uses) — the AI's recommendation is
provably the same a human would see.

CREATE_PURCHASE_ORDER has two deterministic branches:
- items specified: resolve supplier + products -> create the draft PO.
- no items ("prepare a PO for everything likely to run out"): low-stock
  driven procurement — list low-stock products, rank suppliers per product,
  pick the supplier that wins the most products, and build the PO from
  reorder quantities at that supplier's on-file prices.
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import runner
from app.agents.runner import extract
from app.agents.state import AgentState
from app.core.llm.base import LLMProvider


class PurchaseOrderItemExtraction(BaseModel):
    product_query: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0)


class PurchaseOrderExtraction(BaseModel):
    supplier_query: str | None = Field(default=None, max_length=200)
    items: list[PurchaseOrderItemExtraction] = Field(default_factory=list)


class ProductQueryExtraction(BaseModel):
    query: str = Field(default="", max_length=200)


PO_EXTRACT_SYSTEM_PROMPT = (
    "Extract the purchase order request into `extract_purchase_order`: the "
    "supplier (`supplier_query`, when named) and the line items as "
    "`product_query` with `quantity`. If the request says to buy everything "
    "that is running low (e.g. \"prepare a purchase order for everything "
    "likely to run out\"), leave `items` empty — the workflow decides what to "
    "buy. Never invent products, quantities or suppliers."
)


def build_compare_suppliers_workflow(provider: LLMProvider, db: AsyncSession):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def extract_node(state: AgentState) -> dict[str, Any]:
        updates, extraction = await extract(
            provider,
            state,
            tool_name="extract_product_query",
            tool_description="Extract which product's supplier offers to compare.",
            schema=ProductQueryExtraction,
            system_prompt=(
                "Extract the product the user wants supplier prices for into "
                "`extract_product_query` (`query`). Use their own words."
            ),
        )
        if extraction is None:
            return updates
        return {**updates, "extraction": extraction.model_dump()}

    async def compare_node(state: AgentState) -> dict[str, Any]:
        query = state.get("extraction", {}).get("query", "")
        products_result = await runner.run_tool(state, db, "search_products", {"query": query})
        if not products_result.get("ok"):
            return {"error": f"Could not search products: {products_result.get('error')}"}
        products = products_result["data"].get("products", [])
        if not products:
            return {"reply": f"No product matches '{query}'.", "result": {"offers": []}}
        product = products[0]
        compare_result = await runner.run_tool(
            state, db, "compare_supplier_prices", {"product_id": product["product_id"]}
        )
        if not compare_result.get("ok"):
            return {"error": f"Could not compare suppliers: {compare_result.get('error')}"}
        offers = compare_result["data"].get("offers", [])
        if not offers:
            return {
                "reply": f"No supplier offers on file for {product['name']}.",
                "result": {"product": product, "offers": []},
            }
        best = offers[0]
        lines = "; ".join(
            f"{offer['supplier_name']} at {offer['price']} (lead {offer['lead_time_days']}d)"
            for offer in offers
        )
        return {
            "reply": (
                f"For {product['name']}, the best offer is {best['supplier_name']} at "
                f"{best['price']} (lead {best['lead_time_days']} days). Full ranking: {lines}"
            ),
            "result": {"product": product, "offers": offers},
        }

    graph.add_node("extract", extract_node)
    graph.add_node("compare", compare_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "compare")
    graph.add_edge("compare", END)
    return graph.compile()


async def _resolve_supplier(state: AgentState, db: AsyncSession, supplier_query: str) -> dict[str, Any] | None:
    result = await runner.run_tool(state, db, "search_suppliers", {"query": supplier_query})
    if not result.get("ok"):
        return {"error": f"Could not search suppliers: {result.get('error')}"}
    suppliers = result["data"].get("suppliers", [])
    if not suppliers:
        return {"error": f"No supplier matches '{supplier_query}'."}
    return suppliers[0]


async def _low_stock_plan(
    state: AgentState, db: AsyncSession
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Low-stock-driven procurement. Returns (supplier_id, items, narration, error)."""
    low_result = await runner.run_tool(state, db, "list_low_stock", {})
    if not low_result.get("ok"):
        return "", [], [], f"Could not check stock: {low_result.get('error')}"
    low_items = low_result["data"].get("items", [])
    if not low_items:
        return "", [], [], None

    best_by_product: list[dict[str, Any]] = []
    supplier_wins: dict[str, dict[str, Any]] = {}
    for item in low_items:
        compare_result = await runner.run_tool(
            state, db, "compare_supplier_prices", {"product_id": item["product_id"]}
        )
        if not compare_result.get("ok"):
            continue
        offers = compare_result["data"].get("offers", [])
        if not offers:
            continue
        best = offers[0]
        quantity = item["reorder_quantity"] or 1
        best_by_product.append(
            {
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "quantity": quantity,
                "unit_cost": best["price"],
                "supplier_id": best["supplier_id"],
            }
        )
        supplier_wins.setdefault(
            best["supplier_id"],
            {"supplier_id": best["supplier_id"], "supplier_name": best["supplier_name"], "wins": 0},
        )
        supplier_wins[best["supplier_id"]]["wins"] += 1

    if not best_by_product:
        return "", [], [], None
    # The supplier that wins the most products; ties broken by name for determinism.
    top_supplier = sorted(
        supplier_wins.values(), key=lambda s: (-s["wins"], s["supplier_name"])
    )[0]
    items = [item for item in best_by_product if item["supplier_id"] == top_supplier["supplier_id"]]
    return top_supplier["supplier_id"], items, best_by_product, None


def build_create_purchase_order_workflow(provider: LLMProvider, db: AsyncSession):
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AgentState)

    async def extract_node(state: AgentState) -> dict[str, Any]:
        updates, extraction = await extract(
            provider,
            state,
            tool_name="extract_purchase_order",
            tool_description="Extract supplier and line items from a purchase order request.",
            schema=PurchaseOrderExtraction,
            system_prompt=PO_EXTRACT_SYSTEM_PROMPT,
        )
        if extraction is None:
            return updates
        return {**updates, "extraction": extraction.model_dump()}

    async def plan_node(state: AgentState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        extraction = state.get("extraction", {})
        supplier_query = extraction.get("supplier_query")
        items = extraction.get("items", [])

        supplier_id: str | None = None
        plan_items: list[dict[str, Any]] = []
        narration: list[str] = []

        if items:
            if not supplier_query:
                return {"reply": "Which supplier should I place this purchase order with?"}
            supplier = await _resolve_supplier(state, db, supplier_query)
            if supplier is None or "error" in supplier:
                return {"reply": supplier["error"]}
            supplier_id = supplier["supplier_id"]
            for line in items:
                products_result = await runner.run_tool(
                    state, db, "search_products", {"query": line["product_query"]}
                )
                products = products_result.get("data", {}).get("products", []) if products_result.get("ok") else []
                if not products:
                    return {"reply": f"No product matches '{line['product_query']}'."}
                product = next((p for p in products if p.get("is_active")), products[0])
                plan_items.append(
                    {"product_id": product["product_id"], "quantity": line["quantity"]}
                )
                narration.append(f"{line['quantity']} x {product['name']}")
        else:
            supplier_id, plan_items, best_by_product, plan_error = await _low_stock_plan(state, db)
            if plan_error:
                return {"error": plan_error}
            if not supplier_id:
                return {
                    "reply": "No products are running low, so there is nothing to reorder right now.",
                    "result": {"purchase_order": None},
                }
            narration = [
                f"{item['quantity']} x {item['product_name']} (reorder qty at {item['unit_cost']})"
                for item in best_by_product
            ]

        return {
            "supplier_id": supplier_id,
            "plan_items": plan_items,
            "plan_narration": narration,
        }

    async def create_node(state: AgentState) -> dict[str, Any]:
        if state.get("error") or not state.get("supplier_id"):
            return {}
        result = await runner.run_tool(
            state,
            db,
            "create_purchase_order",
            {
                "supplier_id": state["supplier_id"],
                "items": [{"product_id": item["product_id"], "quantity": item["quantity"]} for item in state["plan_items"]],
            },
        )
        if not result.get("ok"):
            return {"error": f"Purchase order could not be created: {result.get('error')}"}
        return {"created_po_id": result["data"]["purchase_order_id"]}

    async def verify_node(state: AgentState) -> dict[str, Any]:
        if state.get("error") or not state.get("created_po_id"):
            return {}
        result = await runner.run_tool(state, db, "list_purchase_orders", {})
        if not result.get("ok"):
            return {"error": f"Verification failed: {result.get('error')}"}
        pos = result["data"].get("purchase_orders", [])
        found = next((po for po in pos if po["purchase_order_id"] == state["created_po_id"]), None)
        if found is None or found["status"] != "DRAFT":
            return {"error": "Verification failed: purchase order not found as DRAFT."}
        return {"verified": True}

    async def summarize_node(state: AgentState) -> dict[str, Any]:
        if state.get("reply"):
            return {}
        if state.get("error"):
            return {"reply": f"Sorry — I couldn't complete the purchase order: {state['error']}"}
        if not state.get("verified"):
            return {"reply": "Sorry — the purchase order was created but verification failed."}
        narration = ", ".join(state["plan_narration"])
        return {
            "reply": (
                f"Purchase order {state['created_po_id'][:8]} drafted for {narration}. "
                "It's a DRAFT — review it and send it when ready. Verified."
            ),
            "result": {"purchase_order_id": state["created_po_id"], "items": state["plan_narration"]},
        }

    graph.add_node("extract", extract_node)
    graph.add_node("plan", plan_node)
    graph.add_node("create", create_node)
    graph.add_node("verify", verify_node)
    graph.add_node("summarize", summarize_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "plan")
    graph.add_edge("plan", "create")
    graph.add_edge("create", "verify")
    graph.add_edge("verify", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()