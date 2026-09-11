"""Document ingestion pipeline (Phase 7, FR-21).

`ingest` takes validated upload bytes + metadata and runs the deterministic
pipeline: store the `Document` row, chunk the extracted text, embed each
chunk, and persist `DocumentChunk` rows (pgvector). All in one transaction
so a failed embed never leaves half a document.

Supported upload types (the allow-list in `app/api/documents.py`):
text-based .txt/.md/.csv/.json plus PDF and DOCX, all parsed
deterministically by `app/services/extraction.py` (Phase 9).

`delete` is a soft delete so historical RAG citations stay resolvable.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.embeddings import EmbeddingProvider, get_embedding_provider
from app.database.base import utcnow
from app.models.document import Document, DocumentChunk
from app.services.chunking import chunk_text
from app.services.errors import BusinessRuleError
from app.services.extraction import extract_text

logger = logging.getLogger(__name__)


async def ingest_document(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    uploaded_by_user_id: uuid.UUID,
    filename: str,
    content_type: str,
    content: bytes,
    provider: EmbeddingProvider | None = None,
    title: str | None = None,
) -> Document:
    """Store a document, chunk its text, embed the chunks, and persist them."""
    text = extract_text(content_type=content_type, content=content)
    if not text.strip():
        raise BusinessRuleError(422, "Document contains no extractable text")

    doc = Document(
        business_id=business_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        text_content=text,
        title=title,
        uploaded_by_user_id=uploaded_by_user_id,
        processed_at=utcnow(),
    )
    db.add(doc)
    await db.flush()

    provider = provider or get_embedding_provider()
    chunks = chunk_text(text)
    for index, chunk in enumerate(chunks):
        vector = await provider.embed(chunk.content)
        db.add(
            DocumentChunk(
                document_id=doc.id,
                business_id=business_id,
                chunk_index=index,
                content=chunk.content,
                embedding=vector,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
            )
        )
    await db.commit()
    await db.refresh(doc)
    return doc


async def delete_document(db: AsyncSession, business_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """Soft-delete a document (ADR-009): hidden from new retrievals, but its
    chunks remain for historical citations.
    """
    result = await db.execute(
        select(Document).where(
            Document.id == document_id, Document.business_id == business_id
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None or doc.deleted_at is not None:
        raise BusinessRuleError(404, "Document not found")
    doc.deleted_at = utcnow()
    await db.commit()