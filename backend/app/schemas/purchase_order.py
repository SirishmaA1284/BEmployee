import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PurchaseOrderStatus


class PurchaseOrderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    # If omitted, the current supplier_products price for this product is
    # used (see app/services/procurement.py). Explicit override always wins.
    unit_cost: Decimal | None = Field(default=None, ge=0)


class PurchaseOrderCreate(BaseModel):
    supplier_id: uuid.UUID
    items: list[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderItemRead(BaseModel):
    product_id: uuid.UUID
    sku: str
    product_name: str
    quantity: int
    unit_cost: Decimal
    line_total: Decimal


class PurchaseOrderRead(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    status: PurchaseOrderStatus
    subtotal: Decimal
    total: Decimal
    items: list[PurchaseOrderItemRead]
    created_at: datetime
    sent_at: datetime | None
    completed_at: datetime | None
