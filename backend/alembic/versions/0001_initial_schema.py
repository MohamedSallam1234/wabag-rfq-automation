"""initial schema: app_user role, projects, documents

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

# revision identifiers, used by Alembic.
revision: str = '0001_initial'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the least-privilege runtime role and the projects + documents tables."""
    # --- least-privilege runtime role -------------------------------------------------
    # The app connects as `app_user`; the migration role owns the schema. Create the role
    # if absent and grant it future-table DML. Guarded so the migration stays portable on
    # databases where app_user is provisioned out-of-band.
    # APP_USER_PASSWORD is sourced via Settings, so it loads from .env *or* a real env var.
    password = get_settings().APP_USER_PASSWORD.get_secret_value()
    if not password:
        raise RuntimeError(
            "APP_USER_PASSWORD must be set (via .env or the environment) to create the app_user role"
        )
    escaped = password.replace("'", "''")  # Postgres single-quote escape for the literal
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
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_user"
    )

    # --- enum types -------------------------------------------------------------------
    bind = op.get_bind()
    doc_type_source = postgresql.ENUM('auto', 'manual', name='doc_type_source')
    retention_policy = postgresql.ENUM('persistent', 'transient', name='retention_policy')
    doc_type_source.create(bind, checkfirst=True)
    retention_policy.create(bind, checkfirst=True)

    # --- projects ---------------------------------------------------------------------
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('client', sa.String(length=255), nullable=True),
        sa.Column('consultant', sa.String(length=255), nullable=True),
        sa.Column('project_number', sa.String(length=128), nullable=True),
        sa.Column('capacity_m3d', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- documents --------------------------------------------------------------------
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('original_filename', sa.String(length=512), nullable=False),
        sa.Column('storage_bucket', sa.String(length=128), nullable=False),
        sa.Column('storage_path', sa.String(length=1024), nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('doc_type', sa.String(length=64), nullable=True),
        sa.Column(
            'doc_type_source',
            postgresql.ENUM('auto', 'manual', name='doc_type_source', create_type=False),
            server_default='auto',
            nullable=False,
        ),
        sa.Column('revision_label', sa.String(length=32), nullable=True),
        sa.Column('revision_number', sa.Integer(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('sheet_names', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'retention',
            postgresql.ENUM('persistent', 'transient', name='retention_policy', create_type=False),
            server_default='transient',
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_project_id', 'documents', ['project_id'])
    op.create_index('ix_documents_doc_type', 'documents', ['doc_type'])

    # --- grant DML on the new tables to the runtime role (guarded; role may be absent) ---
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON projects, documents TO app_user;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    """Drop the projects + documents tables, the enum types, and the app_user role."""
    op.drop_index('ix_documents_doc_type', table_name='documents')
    op.drop_index('ix_documents_project_id', table_name='documents')
    op.drop_table('documents')
    op.drop_table('projects')
    op.execute('DROP TYPE IF EXISTS retention_policy')
    op.execute('DROP TYPE IF EXISTS doc_type_source')
    op.execute('DROP ROLE IF EXISTS app_user')
