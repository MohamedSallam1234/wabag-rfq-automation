"""add document retention

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-20 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    retention_policy = postgresql.ENUM('persistent', 'transient', name='retention_policy')
    retention_policy.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'documents',
        sa.Column(
            'retention',
            postgresql.ENUM('persistent', 'transient', name='retention_policy', create_type=False),
            server_default='transient',
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'retention')
    op.execute('DROP TYPE IF EXISTS retention_policy')
