"""Deterministic MockProvider (docs/decisions.md ADR-005).

Used by every automated test and as the default provider when no API key is
configured, so the whole suite and the local demo run without network access.

Two behaviours, script first:

1. `script` — an ordered list of canned responses, each either
   `{"tool": name, "arguments": {...}}` (the model calls a tool) or
   `{"content": "..."}` (the model answers in prose). Tests drive the exact
   tool-call sequence an agent should make and assert on it.
2. keyword rules — when no script is set, a small deterministic parser maps
   the canonical demo phrases to tool calls. This is a *test double and demo
   stand-in*, not a second implementation of agent logic: production uses the
   configured real provider (OpenAI by default).
"""

import re
from collections.abc import Sequence
from typing import Any

from app.core.llm.base import LLMProvider, LLMResponse, ToolCallRequest, ToolCallResult

_UNIT_WORDS = {
    "packet", "packets", "pack", "packs", "bag", "bags", "bottle", "bottles",
    "box", "boxes", "unit", "units", "piece", "pieces", "kg", "gm", "g",
    "ml", "l", "litre", "litres", "dozen",
}

# Quantity phrases that are not products ("within 7 days", "everything") —
# parsed out and dropped so they never become phantom line items.
_FILLER_PHRASES = {
    "days", "day", "weeks", "week", "months", "month", "items", "products",
    "things", "everything", "of everything", "units of everything",
}


def _strip_trailing_unit(phrase: str) -> str:
    words = phrase.strip().split()
    while words and words[-1].lower() in _UNIT_WORDS:
        words.pop()
    return " ".join(words).strip()


def _after(message: str, *markers: str) -> str | None:
    lowered = message.lower()
    for marker in markers:
        if marker in lowered:
            return message[lowered.index(marker) + len(marker):].strip()
    return None


def _parse_items(message: str) -> list[dict[str, Any]] | None:
    """Parses "3 coffee packets and 2 sugar bags" -> item list. Returns None
    when the message has no recognizable "<quantity> <phrase>" patterns.
    """
    lowered = message.lower().rstrip(" .!?")
    items: list[dict[str, Any]] = []
    # Separators: start of string, a word boundary (so the first item can
    # follow "containing"), punctuation, or "and".
    for match in re.finditer(
        r"(?:^|\b|[,;])\s*(\d+)\s+([a-z][a-z ]{1,40}?)(?=,|;|\band\b|$)", lowered
    ):
        quantity = int(match.group(1))
        product_query = _strip_trailing_unit(match.group(2))
        if product_query and product_query not in _FILLER_PHRASES:
            items.append({"product_query": product_query, "quantity": quantity})
    if not items:
        return None
    # Remove trailing filler words ("items", "only", "please", ".") from the
    # last product phrase.
    last = items[-1]["product_query"]
    for filler in (" please", " only", "."):
        if last.endswith(filler):
            items[-1]["product_query"] = last[: -len(filler)].strip()
    return items


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, script: Sequence[dict[str, Any]] | None = None) -> None:
        self._script = list(script) if script else []
        self._script_index = 0

    def _next_scripted(self) -> dict[str, Any] | None:
        if self._script_index < len(self._script):
            step = self._script[self._script_index]
            self._script_index += 1
            return step
        return None

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        tools: list[ToolCallRequest] | None = None,
    ) -> LLMResponse:
        user_message = messages[-1]["content"] if messages else ""

        scripted = self._next_scripted()
        if scripted is not None:
            if "tool" in scripted:
                return LLMResponse(
                    tool_calls=[
                        ToolCallResult(
                            name=scripted["tool"], arguments=scripted.get("arguments", {})
                        )
                    ]
                )
            return LLMResponse(content=scripted["content"])

        if tools:
            for tool in tools:
                arguments = _keyword_arguments(tool.name, user_message)
                if arguments is not None:
                    return LLMResponse(tool_calls=[ToolCallResult(name=tool.name, arguments=arguments)])

        return LLMResponse(
            content=(
                "I can help with orders, inventory, suppliers and purchase orders. "
                "Try: \"Create an order for Rahul with 3 coffee packets\", "
                "\"Which products are running low?\", or \"Compare supplier prices for coffee\"."
            )
        )


def _keyword_arguments(tool_name: str, message: str) -> dict[str, Any] | None:
    lowered = message.lower()

    if tool_name == "classify_intent":
        # "Prepare a purchase order for everything likely to run out" is a
        # procurement request even though it mentions running out.
        if "purchase order" in lowered or "reorder" in lowered or "procure" in lowered:
            return {"intent": "CREATE_PURCHASE_ORDER", "summary": "Prepare a purchase order"}
        if "low stock" in lowered or "running low" in lowered or "run out" in lowered:
            return {"intent": "LOW_STOCK", "summary": "Identify products at or below reorder threshold"}
        if "compare" in lowered or "best price" in lowered or "cheapest" in lowered:
            return {"intent": "COMPARE_SUPPLIERS", "summary": "Compare supplier offers for a product"}
        if "order for" in lowered or "create an order" in lowered or "new order" in lowered or "place an order" in lowered:
            return {"intent": "CREATE_ORDER", "summary": "Create a customer order"}
        if "sales" in lowered or "report" in lowered or "revenue" in lowered:
            return {"intent": "SALES_REPORT", "summary": "Summarize sales activity"}
        if "product" in lowered and ("search" in lowered or "find" in lowered or "list" in lowered):
            return {"intent": "SEARCH_PRODUCTS", "summary": "Search the product catalog"}
        if "stock" in lowered or "inventory" in lowered or "quantity" in lowered:
            return {"intent": "CHECK_INVENTORY", "summary": "Check current inventory levels"}
        if "customer" in lowered and ("search" in lowered or "find" in lowered):
            return {"intent": "SEARCH_CUSTOMERS", "summary": "Search customers"}
        return {"intent": "UNKNOWN", "summary": "Could not determine what the user wants"}

    if tool_name == "extract_order":
        after = _after(message, "for ", "from ")
        customer_query = None
        if after:
            for stop in (" containing", " with", " including", ":"):
                if stop in after:
                    after = after[: after.index(stop)].strip()
                    break
            customer_query = _strip_trailing_unit(after) or None
        items = _parse_items(message)
        if items is None:
            return None
        return {"customer_query": customer_query, "items": items}

    if tool_name == "extract_purchase_order":
        items = _parse_items(message)
        after = _after(message, "from ", "to ")
        if after:
            for stop in (" for ", " with ", " containing "):
                if stop in after:
                    after = after[: after.index(stop)].strip()
                    break
            supplier_query = _strip_trailing_unit(after) or None
        else:
            supplier_query = None
        # "for everything likely to run out" style requests carry no items —
        # the workflow falls back to low-stock-driven procurement.
        if items is None:
            return {"supplier_query": supplier_query, "items": []}
        return {"supplier_query": supplier_query, "items": items}

    if tool_name in ("extract_product_query", "extract_search_query"):
        # "containing"/"matching" come before the generic "for" so that
        # "search for products containing coffee" extracts "coffee".
        for marker in ("best price for ", "price for ", "containing ", "matching ", "about ", "for "):
            after = _after(message, marker)
            if after:
                query = _strip_trailing_unit(after)
                query = query.strip(" ?.!")
                if query:
                    return {"query": query}
        return None

    return None