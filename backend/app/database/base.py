import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Shared declarative base. All ORM models live under app.models and are
    imported by app.models.__init__ so Alembic autogenerate can see them.
    """


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SoftDeleteMixin:
    """For entities historical records may still reference (products,
    customers, suppliers) — see docs/decisions.md ADR-009. Queries that
    should exclude deleted rows must filter `deleted_at.is_(None)`
    explicitly; there is no automatic global filter (keeps query behavior
    explicit and auditable rather than "magic").
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
