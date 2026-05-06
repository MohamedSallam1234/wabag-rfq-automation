"""grant bypassrls to app_user

Revision ID: ba4aae8587af
Revises: b7416cc103c2
Create Date: 2026-05-03 15:18:43.068285

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ba4aae8587af'
down_revision: Union[str, Sequence[str], None] = 'b7416cc103c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER ROLE app_user BYPASSRLS;")

def downgrade() -> None:
    op.execute("ALTER ROLE app_user NOBYPASSRLS;")
