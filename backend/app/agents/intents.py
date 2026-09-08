"""Intent classification — the orchestrator's first node (FR-11).

The classifier is a structured LLM call whose output is validated against
`AgentIntent` before routing; an invalid or missing classification routes to
the UNKNOWN/clarify branch. Prompt-layer only — no tools, no DB.
"""

from pydantic import BaseModel

from app.core.llm.base import ToolCallRequest
from app.models.enums import AgentIntent

CLASSIFY_SYSTEM_PROMPT = """You are the AI Employee for a small retail business.
Classify the user's request into exactly one intent. Respond only with a tool
call to `classify_intent` providing `intent` (one of the enum values below)
and a one-sentence `summary` restating what the user asked.

Intents:
- CREATE_ORDER: the user wants to place/sell an order for one or more products
  to a customer ("create an order for Rahul with 3 coffee").
- CHECK_INVENTORY: the user asks about current stock levels or quantities
  ("how much coffee do we have", "check stock").
- LOW_STOCK: the user asks what is running low or about to run out
  ("which products are running low").
- COMPARE_SUPPLIERS: the user asks which supplier is best/cheapest for a
  product ("which supplier gives the best price for coffee").
- CREATE_PURCHASE_ORDER: the user wants to reorder stock from a supplier
  ("prepare a purchase order for low stock items", "order more sugar from
  Metro").
- SEARCH_PRODUCTS: the user wants to look up products in the catalog.
- SEARCH_CUSTOMERS: the user wants to look up a customer.
- SALES_REPORT: the user asks about sales, revenue or outstanding payments.
- ASK_DOCUMENTS: the user asks a question that can be answered from the
  business's uploaded documents (policies, price lists, contracts, notes)
  ("what does our return policy say", "ask the docs about X"). When the
  question is about uploaded business documents, prefer this over the other
  intents.
- UNKNOWN: anything else — never guess. Pick UNKNOWN when none of the above
  clearly fits."""


class IntentClassification(BaseModel):
    intent: AgentIntent
    summary: str


CLASSIFY_TOOL = ToolCallRequest(
    name="classify_intent",
    description="Classify the user's request into one business intent.",
    input_schema=IntentClassification.model_json_schema(),
)