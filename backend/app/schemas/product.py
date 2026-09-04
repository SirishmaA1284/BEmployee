import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    unit: str = Field(default="unit", min_length=1, max_length=32)
    unit_price: Decimal = Field(ge=0)
    cost_price: Decimal | None = Field(default=None, ge=0)
    reorder_threshold: int = Field(default=0, ge=0)
    reorder_quantity: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    unit_price: Decimal | None = Field(default=None, ge=0)
    cost_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    reorder_threshold: int | None = Field(default=None, ge=0)
    reorder_quantity: int | None = Field(default=None, ge=0)


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    description: str | None
    unit: str
    unit_price: Decimal
    cost_price: Decimal | None
    is_active: bool
