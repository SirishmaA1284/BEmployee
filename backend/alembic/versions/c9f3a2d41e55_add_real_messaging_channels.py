"""add real messaging channels to notification_channel enum

Revision ID: c9f3a2d41e55
Revises: b1244bf28ccb
Create Date: 2026-09-09 12:00:00.000000

Adds TELEGRAM/WHATSAPP (real delivery rows) and MOCK_TELEGRAM (fallback)
to the `notification_channel` enum. Postgres enum values cannot be
removed without recreating the type, so downgrade is a no-op (matching
the existing NOTIFICATION_SENT pattern in 05beb7c32bed).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9f3a2d41e55'
down_revision: Union[str, None] = 'b1244bf28ccb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_channel ADD VALUE IF NOT EXISTS 'TELEGRAM'")
    op.execute("ALTER TYPE notification_channel ADD VALUE IF NOT EXISTS 'WHATSAPP'")
    op.execute("ALTER TYPE notification_channel ADD VALUE IF NOT EXISTS 'MOCK_TELEGRAM'")


def downgrade() -> None:
    # Postgres enum values cannot be dropped without recreating the type;
    # harmless if unused (same policy as audit_action.NOTIFICATION_SENT).
    pass