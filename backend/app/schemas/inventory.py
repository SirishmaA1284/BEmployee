import uuid

from pydantic import BaseModel, Field, field_validator


class InventoryRead(BaseModel):
    product_id: uuid.UUID
    sku: str
    product_name: str
    quantity_on_hand: int
    reorder_threshold: int
    reorder_quantity: int
    is_low_stock: bool


class StockAdjustmentRequest(BaseModel):
    change_quantity: int = Field(description="Positive to increase, negative to decrease.")
    note: str | None = Field(default=None, max_length=500)

    @field_validator("change_quantity")
    @classmethod
    def not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("change_quantity must not be zero")
        return value
