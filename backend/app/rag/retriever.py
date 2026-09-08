"""RAG retrieval (Phase 7, FR-21/22/23, docs/decisions.md ADR-006).

`retrieve` embeds a query and runs a pgvector cosine-similarity search over
a business's `document_chunks`, returning top-k chunks tagged with their
source document for citation. Business scoping is enforced by the query
filter — a chunk from another business can never match.

The returned chunks are *data*, not instructions (FR-23): the agent wraps
them in the delimited UNTRUSTED block before sending them to the LLM, and
the answer must cite the documents that informed it (FR-22).
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.embeddings import EmbeddingProvider, get_embedding_provider
from app.models.document import Document, DocumentChunk

DEFAULT_TOP_K = 4


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    start_char: int
    end_char: int
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "document_id": str(self.document_id),
            "document_name": self.document_name,
            "chunk_index": self.chunk_index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "similarity": round(self.similarity, 4),
        }


async def retrieve(
    db: AsyncSession,
    business_id: uuid.UUID,
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    provider: EmbeddingProvider | None = None,
) -> list[RetrievedChunk]:
    """Embed `query` and return the business's top-k most similar chunks."""
    provider = provider or get_embedding_provider()
    query_vector = await provider.embed(query)
    if not any(query_vector):
        return []

    # pgvector <=> operator = cosine distance; 1 - distance = similarity.
    # Filter to this business + non-deleted documents only.
    statement = (
        select(
            DocumentChunk,
            Document.filename,
            (1 - DocumentChunk.embedding.cosine_distance(query_vector)).label("similarity"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.business_id == business_id,
            Document.deleted_at.is_(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
        .limit(top_k)
    )
    result = await db.execute(statement)
    chunks = []
    for chunk, filename, similarity in result.all():
        chunks.append(
            RetrievedChunk(
                content=chunk.content,
                document_id=chunk.document_id,
                document_name=filename,
                chunk_index=chunk.chunk_index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                similarity=similarity,
            )
        )
    return chunks