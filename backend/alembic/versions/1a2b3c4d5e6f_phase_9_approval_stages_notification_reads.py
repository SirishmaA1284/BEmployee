"""phase 9: approval stages, notification read state

Revision ID: 1a2b3c4d5e6f
Revises: c9f3a2d41e55
Create Date: 2026-09-11 09:00:00.000000

Adds:
- `approval_request_steps`: sequential decision stages for multi-stage
  (chained) approval requests (Phase 9). Reuses the existing
  `approval_status` PG enum (create_type=False).
- `approval_requests.required_stages`: total stages required (default 1 =
  single-decision Phase 5 behavior).
- `policy_type` enum value `APPROVAL_STAGES` (business policy configuring
  the chain length).
- `notification_reads`: per-user read markers (composite PK) so each
  business member tracks their own read state on business-scoped
  notifications.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = 'c9f3a2d41e55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('approval_request_steps',
    sa.Column('approval_request_id', sa.UUID(), nullable=False),
    sa.Column('stage_number', sa.Integer(), nullable=False),
    sa.Column('status', postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', name='approval_status', create_type=False), nullable=False),
    sa.Column('required_roles', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('resolved_by_user_id', sa.UUID(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['approval_request_id'], ['approval_requests.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_approval_request_steps_approval_request_id', 'approval_request_steps', ['approval_request_id'], unique=False)

    op.add_column('approval_requests', sa.Column('required_stages', sa.Integer(), server_default='1', nullable=False))

    op.execute("ALTER TYPE policy_type ADD VALUE IF NOT EXISTS 'APPROVAL_STAGES'")

    op.create_table('notification_reads',
    sa.Column('notification_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('notification_id', 'user_id')
    )


def downgrade() -> None:
    # Postgres enum values cannot be dropped without recreating the type;
    # harmless if unused (same policy as the notification_channel additions).
    op.drop_table('notification_reads')
    op.drop_column('approval_requests', 'required_stages')
    op.drop_index('ix_approval_request_steps_approval_request_id', table_name='approval_request_steps')
    op.drop_table('approval_request_steps')