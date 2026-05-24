"""create projects and documents

Revision ID: f1a2b3c4d5e6
Revises: ba4aae8587af
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = 'ba4aae8587af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    doc_type_source = postgresql.ENUM('auto', 'manual', name='doc_type_source')
    document_status = postgresql.ENUM(
        'pending', 'processing', 'ready', 'failed', name='document_status'
    )
    doc_type_source.create(bind, checkfirst=True)
    document_status.create(bind, checkfirst=True)

    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('client', sa.String(length=255), nullable=True),
        sa.Column('consultant', sa.String(length=255), nullable=True),
        sa.Column('project_number', sa.String(length=128), nullable=True),
        sa.Column('capacity_m3d', sa.Integer(), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_projects_owner_id', 'projects', ['owner_id'])

    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('original_filename', sa.String(length=512), nullable=False),
        sa.Column('storage_bucket', sa.String(length=128), nullable=False),
        sa.Column('storage_path', sa.String(length=1024), nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('sha256', sa.String(length=64), nullable=True),
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
            'status',
            postgresql.ENUM(
                'pending', 'processing', 'ready', 'failed',
                name='document_status', create_type=False,
            ),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('failure_reason', sa.String(length=255), nullable=True),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_project_id', 'documents', ['project_id'])
    op.create_index('ix_documents_doc_type', 'documents', ['doc_type'])
    op.create_index('ix_documents_uploaded_by', 'documents', ['uploaded_by'])

    # The runtime role (app_user) connects with least privilege. ALTER DEFAULT
    # PRIVILEGES may not cover tables created by the migration role, so grant DML
    # explicitly. PKs are client-side UUIDs, so no sequence grants are needed.
    # Guarded with a role-existence check so the migration stays portable on databases
    # where app_user was not provisioned (mirrors the guard in b67bd39c4d4c).
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
    """Downgrade schema."""
    op.drop_table('documents')
    op.drop_table('projects')
    op.execute('DROP TYPE IF EXISTS document_status')
    op.execute('DROP TYPE IF EXISTS doc_type_source')
