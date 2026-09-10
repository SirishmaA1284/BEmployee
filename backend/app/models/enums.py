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
    """Full FR-9 lifecycle (Phase 5, ADR-015):

    DRAFT -> PENDING_APPROVAL -> APPROVED -> SENT -> COMPLETED, or CANCELLED
    at any point before COMPLETED. A purchase order that does not need
    approval skips PENDING_APPROVAL and is created directly in DRAFT
    (approval is required when the policy engine classifies the action
    MEDIUM-with-threshold or HIGH — see app/policies).
    """

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
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
    ASK_DOCUMENTS = "ASK_DOCUMENTS"
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
    PENDING = "PENDING"


class ApprovalStatus(str, enum.Enum):
    """Lifecycle of an approval request (FR-18). PENDING is awaiting a human
    decision; there is no code path for an agent to mark its own request
    approved — resolution is always an authenticated human action.
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PolicyType(str, enum.Enum):
    """Kinds of business policies stored in business_policies (FR-16). The
    policy engine evaluates these deterministically — never by asking the
    LLM. Each policy is a key/value row; the `value` JSONB holds the
    threshold or rule the deterministic engine reads.

    MONEY_THRESHOLD: actions whose computed money impact meets/exceeds the
        `amount` value are escalated (MEDIUM -> HIGH).
    APPROVAL_ROLES: which roles may approve a given risk level
        (value = list of role codes, e.g. ["OWNER","ADMIN"]).
    """

    MONEY_THRESHOLD = "MONEY_THRESHOLD"
    APPROVAL_ROLES = "APPROVAL_ROLES"


class AuditAction(str, enum.Enum):
    """Actions recorded in the unified audit_logs table (FR-25). Every
    state-changing action — human or AI — writes one row: actor, action,
    target, business, timestamp, before/after summary.
    """

    LOGIN = "LOGIN"
    BUSINESS_CREATE = "BUSINESS_CREATE"
    MEMBER_INVITE = "MEMBER_INVITE"
    PRODUCT_CREATE = "PRODUCT_CREATE"
    PRODUCT_UPDATE = "PRODUCT_UPDATE"
    PRODUCT_DELETE = "PRODUCT_DELETE"
    INVENTORY_ADJUST = "INVENTORY_ADJUST"
    CUSTOMER_CREATE = "CUSTOMER_CREATE"
    SUPPLIER_CREATE = "SUPPLIER_CREATE"
    SUPPLIER_LINK = "SUPPLIER_LINK"
    ORDER_CREATE = "ORDER_CREATE"
    ORDER_CANCEL = "ORDER_CANCEL"
    INVOICE_PAY = "INVOICE_PAY"
    PURCHASE_ORDER_CREATE = "PURCHASE_ORDER_CREATE"
    PURCHASE_ORDER_SEND = "PURCHASE_ORDER_SEND"
    PURCHASE_ORDER_RECEIVE = "PURCHASE_ORDER_RECEIVE"
    PURCHASE_ORDER_CANCEL = "PURCHASE_ORDER_CANCEL"
    POLICY_UPSERT = "POLICY_UPSERT"
    APPROVAL_DECIDE = "APPROVAL_DECIDE"
    AGENT_ACTION = "AGENT_ACTION"
    NOTIFICATION_SENT = "NOTIFICATION_SENT"
    DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD"
    DOCUMENT_DELETE = "DOCUMENT_DELETE"


class NotificationType(str, enum.Enum):
    """Kinds of notifications the worker / backend create (FR-24, docs/decisions.md
    ADR-007). `category` drives how the UI groups them; `severity` drives how
    prominently they are shown. All of these are created by backend logic —
    never by the LLM.
    """

    LOW_STOCK = "LOW_STOCK"
    FORECASTED_STOCKOUT = "FORECASTED_STOCKOUT"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    DAILY_REPORT = "DAILY_REPORT"


class NotificationSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class NotificationChannel(str, enum.Enum):
    """Delivery channels for a notification. IN_APP is always written; the
    MOCK channels exist for the messaging mock (docs/decisions.md A6) and
    simply log the "sent" message — no real provider credentials needed.
    TELEGRAM/WHATSAPP rows record a real delivery attempt when the
    corresponding credentials are configured (app/services/messaging.py).
    """

    IN_APP = "IN_APP"
    TELEGRAM = "TELEGRAM"
    WHATSAPP = "WHATSAPP"
    MOCK_TELEGRAM = "MOCK_TELEGRAM"
    MOCK_WHATSAPP = "MOCK_WHATSAPP"
    MOCK_SMS = "MOCK_SMS"
    MOCK_EMAIL = "MOCK_EMAIL"
