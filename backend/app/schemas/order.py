import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import OrderStatus
from app.schemas.customer import CustomerCreate


class OrderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    customer_id: uuid.UUID | None = None
    # Phase 10: inline customer creation — provide exactly one of
    # `customer_id` (existing customer) or `customer` (find-or-create).
    customer: CustomerCreate | None = None
    items: list[OrderItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def exactly_one_customer(self) -> "OrderCreate":
        if (self.customer_id is None) == (self.customer is None):
            raise ValueError("Provide exactly one of customer_id or customer")
        return self


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
