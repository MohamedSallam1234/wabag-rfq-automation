"""create app_user role

Revision ID: b67bd39c4d4c
Revises:
Create Date: 2026-05-03 13:26:36.952116

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b67bd39c4d4c'  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    password = os.environ["APP_USER_PASSWORD"]
    # Postgres single-quote escape for role password literal
    escaped = password.replace("'", "''")
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                CREATE ROLE app_user LOGIN PASSWORD '{escaped}';
            END IF;
        END
        $$
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO app_user")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_user")

def downgrade() -> None:
    op.execute("DROP ROLE IF EXISTS app_user;")
