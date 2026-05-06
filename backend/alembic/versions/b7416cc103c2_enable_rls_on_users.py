"""enable rls on users

Revision ID: b7416cc103c2
Revises: 7ceac6b279af
Create Date: 2026-05-03 15:14:07.619802

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7416cc103c2'  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = '7ceac6b279af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    # SELECT: users can read their own profile
    op.execute("CREATE POLICY users_select_own ON users FOR SELECT USING (id = auth.uid())")
    # UPDATE: users can update their own profile
    op.execute("CREATE POLICY users_update_own ON users FOR UPDATE USING (id = auth.uid())")
    # No INSERT policy — only the trigger creates rows (runs as postgres, bypasses RLS)
    # No DELETE policy — users shouldn't delete their own profiles directly;
    #   deletion happens via auth.users cascade or admin action

def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS users_select_own ON users")
    op.execute("DROP POLICY IF EXISTS users_update_own ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
