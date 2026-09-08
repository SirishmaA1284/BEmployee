"""phase 7: documents + document_chunks (pgvector)

Revision ID: abf9dcb55aed
Revises: 05beb7c32bed
Create Date: 2026-09-08 17:21:43.463508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import pgvector.sqlalchemy.vector  # noqa: F401  provides VECTOR DDL type

# revision identifiers, used by Alembic.
revision: str = 'abf9dcb55aed'
down_revision: Union[str, None] = '05beb7c32bed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New audit actions for document operations, and the ASK_DOCUMENTS agent
    # intent (both via ALTER TYPE ... ADD VALUE, same pattern as Phase 5/6).
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'DOCUMENT_UPLOAD'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'DOCUMENT_DELETE'")
    op.execute("ALTER TYPE agent_intent ADD VALUE IF NOT EXISTS 'ASK_DOCUMENTS'")

    op.create_table('documents',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=128), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('text_content', sa.Text(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('metadata_', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('uploaded_by_user_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('document_chunks',
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
    sa.Column('start_char', sa.Integer(), nullable=False),
    sa.Column('end_char', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # HNSW index for cosine similarity retrieval (docs/decisions.md ADR-006).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding", table_name="document_chunks")
    op.drop_table('document_chunks')
    op.drop_table('documents')
    # Added enum values (DOCUMENT_UPLOAD/DOCUMENT_DELETE/ASK_DOCUMENTS) are left
    # in place — Postgres enum values can't be dropped without recreating the type.
