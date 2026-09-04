import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    is_active: bool


class SupplierProductCreate(BaseModel):
    product_id: uuid.UUID
    price: Decimal = Field(gt=0)
    lead_time_days: int = Field(ge=0)


class SupplierProductRead(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    product_name: str
    price: Decimal
    lead_time_days: int


class SupplierPriceComparisonRow(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    is_active: bool
    price: Decimal
    lead_time_days: int
