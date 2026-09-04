import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import StockMovementReason


class StockMovement(UUIDPrimaryKeyMixin, Base):
    """Immutable log of every inventory change (spec FR-6: stock changes must
    be tracked, not just a mutable counter). No updated_at — an audit log
    entry is never edited after the fact.
    """

    __tablename__ = "stock_movements"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    change_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[StockMovementReason] = mapped_column(
        Enum(StockMovementReason, name="stock_movement_reason"), nullable=False
    )
    reference_type: Mapped[str | None] = mapped_column(String(32), default=None)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
