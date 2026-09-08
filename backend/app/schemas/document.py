import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentRead(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    title: str | None
    processed_at: datetime | None
    uploaded_by_user_id: uuid.UUID
    created_at: datetime


class DocumentChunkRead(BaseModel):
    id: uuid.UUID
    chunk_index: int
    content: str
    start_char: int
    end_char: int


class DocumentDetail(DocumentRead):
    chunk_count: int
    chunks: list[DocumentChunkRead]


class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 4


class RAGSource(BaseModel):
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    similarity: float


class RAGQueryResponse(BaseModel):
    answer: str
    sources: list[RAGSource]
    chunks_used: int