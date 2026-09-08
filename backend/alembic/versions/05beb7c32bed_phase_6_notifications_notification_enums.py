"""phase 6: notifications + notification enums

Revision ID: 05beb7c32bed
Revises: d2e271d74b0f
Create Date: 2026-09-08 15:35:17.098016

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '05beb7c32bed'
down_revision: Union[str, None] = 'd2e271d74b0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New audit action for notifications (audit_logs.action enum) — added
    # before any notification row is written (the enum is used by the
    # notification writer, app/services/notification_service.py).
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'NOTIFICATION_SENT'")

    op.create_table('notifications',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('notification_type', sa.Enum('LOW_STOCK', 'FORECASTED_STOCKOUT', 'APPROVAL_PENDING', 'DAILY_REPORT', name='notification_type'), nullable=False),
    sa.Column('severity', sa.Enum('INFO', 'WARNING', 'CRITICAL', name='notification_severity'), nullable=False),
    sa.Column('channel', sa.Enum('IN_APP', 'MOCK_WHATSAPP', 'MOCK_SMS', 'MOCK_EMAIL', name='notification_channel'), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('target_type', sa.String(length=64), nullable=True),
    sa.Column('target_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('notifications')
    # The NOTIFICATION_SENT enum value is left in place (Postgres enum values
    # cannot be dropped without recreating the type; harmless if unused).
