"""Uploaded business documents (FR-21, docs/decisions.md ADR-006).

Unstructured memory: files a business uploads, chunked and embedded
(document_chunks, pgvector) for retrieval-augmented generation. One
`documents` row per upload; one `document_chunks` row per chunk with its
embedding vector and source location (page/offset for citation).

Content is stored as text (extracted at upload time). Raw binary file
handling (PDF parsing, OCR) is out of MVP scope — see docs/decisions.md.
`deleted_at` soft-delete keeps historical RAG citations valid while hiding
the document from new retrievals.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Document(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Original upload content type, checked against an allow-list at upload.
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    # Size in bytes (upload-size limit enforced at upload).
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Extracted plain text the chunks are cut from (also cached here so a
    # deleted upload can still be re-read for citations).
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    # Extracted-at time, i.e. when embedding/chunking completed.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Optional human label / notes (title, category).
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    # Bookkeeping for provenance / re-embedding.
    metadata_: Mapped[dict | None] = mapped_column(JSONB, default=None)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # pgvector column. Fixed 1536-dim to match text-embedding-3-small (the
    # documented default, docs/.env.example EMBEDDING_MODEL); the mock
    # embedding provider emits deterministic 1536-dim vectors so tests run
    # against the same schema and retrieval compares like-for-like.
    embedding: Mapped[list[float]] = mapped_column(
        Vector(1536), nullable=True
    )
    # Source location within the original text for citations.
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="chunks")