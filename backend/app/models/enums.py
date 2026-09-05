import enum


class BusinessRole(str, enum.Enum):
    """A user's role within one specific business (per business_members row).

    Role is per (user_id, business_id), not global on the user — one person
    can be OWNER of one business and EMPLOYEE of another.
    """

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    EMPLOYEE = "EMPLOYEE"


class StockMovementReason(str, enum.Enum):
    SALE = "SALE"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    ADJUSTMENT = "ADJUSTMENT"


class OrderStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(str, enum.Enum):
    ISSUED = "ISSUED"
    PAID = "PAID"
    VOID = "VOID"


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CARD = "CARD"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"
    OTHER = "OTHER"


class PurchaseOrderStatus(str, enum.Enum):
    """DRAFT -> SENT -> COMPLETED, or CANCELLED at any point before COMPLETED.

    PENDING_APPROVAL/APPROVED (spec FR-9) are added in Phase 5 alongside the
    policy/approval engine that actually gates them — see docs/decisions.md
    ADR-015.
    """

    DRAFT = "DRAFT"
    SENT = "SENT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AgentIntent(str, enum.Enum):
    """Intents the orchestrator classifies a chat request into (FR-11).

    Each maps to exactly one workflow graph in app/agents/workflows. The
    classification is a structured LLM call whose output is validated
    against this enum before any routing happens.
    """

    CREATE_ORDER = "CREATE_ORDER"
    CHECK_INVENTORY = "CHECK_INVENTORY"
    LOW_STOCK = "LOW_STOCK"
    COMPARE_SUPPLIERS = "COMPARE_SUPPLIERS"
    CREATE_PURCHASE_ORDER = "CREATE_PURCHASE_ORDER"
    SEARCH_PRODUCTS = "SEARCH_PRODUCTS"
    SEARCH_CUSTOMERS = "SEARCH_CUSTOMERS"
    SALES_REPORT = "SALES_REPORT"
    UNKNOWN = "UNKNOWN"


class AgentSessionStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class AgentTaskStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentActionStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
