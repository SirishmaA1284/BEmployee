"""Documents & RAG API (Phase 7, FR-21/22).

Upload/list/detail/delete of business documents; each upload is chunked and
embedded (pgvector) at ingest time. `POST /api/documents/query` runs a
business-scoped RAG retrieval and returns a cited answer.

Upload validation (docs/security.md): content-type allow-list (text-based
formats only for MVP) + size limit. Document writes are OWNER/ADMIN; reads
and RAG queries are open to any member.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.base import LLMProvider
from app.core.llm.embeddings import EmbeddingProvider, get_embedding_provider
from app.core.llm.providers import get_llm_provider
from app.database.session import get_db
from app.models.business_member import BusinessMember
from app.models.document import Document, DocumentChunk
from app.models.enums import AuditAction, BusinessRole
from app.models.user import User
from app.rag.answer import answer_query
from app.schemas.document import (
    DocumentChunkRead,
    DocumentDetail,
    DocumentRead,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGSource,
)
from app.security.dependencies import get_current_membership, get_current_user, require_role
from app.services.audit_service import record_audit
from app.services.document_service import delete_document, ingest_document
from app.services.errors import BusinessRuleError

router = APIRouter(prefix="/api/documents", tags=["documents"])

_write_role = require_role(BusinessRole.OWNER, BusinessRole.ADMIN)

# Allowed upload content types. Text-based only for MVP — binary formats
# (PDF/DOCX) need extraction tooling documented as out of scope (docs/security.md).
_ALLOWED_CONTENT_TYPES = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/json": ".json",
}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MiB


def _to_read(doc: Document) -> DocumentRead:
    return DocumentRead(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        title=doc.title,
        processed_at=doc.processed_at,
        uploaded_by_user_id=doc.uploaded_by_user_id,
        created_at=doc.created_at,
    )


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    membership: BusinessMember = Depends(_write_role),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        allowed = ", ".join(sorted(_ALLOWED_CONTENT_TYPES))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type '{file.content_type}'. Allowed: {allowed}",
        )
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit",
        )
    if not content.strip():
        raise HTTPException(status_code=422, detail="File is empty")

    try:
        doc = await ingest_document(
            db,
            business_id=membership.business_id,
            uploaded_by_user_id=current_user.id,
            filename=file.filename or "upload.txt",
            content_type=file.content_type,
            content=content,
            title=title,
        )
    except BusinessRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    await record_audit(
        db,
        business_id=membership.business_id,
        actor_type="USER",
        actor_user_id=current_user.id,
        action=AuditAction.DOCUMENT_UPLOAD,
        target_type="document",
        target_id=doc.id,
        summary=f"Uploaded document {doc.filename}",
        after={"filename": doc.filename, "size_bytes": doc.size_bytes},
    )
    await db.commit()
    return _to_read(doc)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentRead]:
    result = await db.execute(
        select(Document)
        .where(Document.business_id == membership.business_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
    )
    return [_to_read(doc) for doc in result.scalars().all()]


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: uuid.UUID,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    result = await db.execute(
        select(Document).where(
            Document.id == document_id, Document.business_id == membership.business_id
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks_result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = [
        DocumentChunkRead(
            id=c.id,
            chunk_index=c.chunk_index,
            content=c.content,
            start_char=c.start_char,
            end_char=c.end_char,
        )
        for c in chunks_result.scalars().all()
    ]
    return DocumentDetail(
        **_to_read(doc).model_dump(),
        chunk_count=len(chunks),
        chunks=chunks,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    document_id: uuid.UUID,
    membership: BusinessMember = Depends(_write_role),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await delete_document(db, membership.business_id, document_id)
    except BusinessRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await record_audit(
        db,
        business_id=membership.business_id,
        actor_type="USER",
        actor_user_id=current_user.id,
        action=AuditAction.DOCUMENT_DELETE,
        target_type="document",
        target_id=document_id,
        summary="Deleted document",
    )
    await db.commit()


@router.post("/query", response_model=RAGQueryResponse)
async def query_documents(
    payload: RAGQueryRequest,
    membership: BusinessMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider),
) -> RAGQueryResponse:
    """Business-scoped RAG retrieval + grounded answer with citations (FR-22).
    Retrieved chunks are wrapped as untrusted data before the LLM sees them
    (FR-23, docs/architecture.md §4).
    """
    result = await answer_query(
        db,
        membership.business_id,
        payload.query,
        top_k=payload.top_k,
        llm=provider,
        embeddings=embeddings,
    )
    return RAGQueryResponse(
        answer=result["answer"],
        sources=[RAGSource(**s) for s in result["sources"]],
        chunks_used=result["chunks_used"],
    )