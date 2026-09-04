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
