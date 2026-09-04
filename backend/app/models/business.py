from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # ISO 4217-ish code; single-currency-per-business for MVP (docs/decisions.md ADR-012).
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)

    members: Mapped[list["BusinessMember"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
