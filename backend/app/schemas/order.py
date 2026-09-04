import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import OrderStatus


class OrderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    customer_id: uuid.UUID
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderItemRead(BaseModel):
    product_id: uuid.UUID
    sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    status: OrderStatus
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    currency: str
    items: list[OrderItemRead]
    invoice_id: uuid.UUID | None
    invoice_number: str | None
    created_at: datetime
