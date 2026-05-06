"""auto-create user profile on signup

Revision ID: 7ceac6b279af
Revises: 9441c9354ef4
Create Date: 2026-05-03 15:11:40.873687

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ceac6b279af'  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = '9441c9354ef4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION public.handle_new_user()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        BEGIN
            INSERT INTO public.users (id, name)
            VALUES (
                NEW.id,
                COALESCE(NEW.raw_user_meta_data->>'name', NEW.email)
            );
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER on_auth_user_created
        AFTER INSERT ON auth.users
        FOR EACH ROW EXECUTE FUNCTION public.handle_new_user()
    """)

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_user()")
