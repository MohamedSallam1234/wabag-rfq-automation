"""ORM model and enums for the ``documents`` table (uploaded source files)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Persist enum *values* (e.g. ``"failed"``) instead of member names (``"FAILED"``).

    SQLAlchemy's ``Enum`` binds the member name by default, which would not match the
    lowercase labels in the Postgres enum type created by the migration.
    """
    return [str(member.value) for member in enum_cls]


class DocTypeSource(StrEnum):
    """Whether a document's classification was set automatically or by an engineer."""

    AUTO = "auto"
    MANUAL = "manual"


class DocumentStatus(StrEnum):
    """Lifecycle of an uploaded document.

    ``pending``: an upload URL was issued, awaiting the client's direct upload.
    ``processing``: the object was uploaded and is being validated in the background.
    ``ready``: validation passed; the file is usable.
    ``failed``: validation failed; the storage object has been removed.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class RetentionPolicy(StrEnum):
    """How long a document's bytes are kept in storage.

    ``persistent``: project-common inputs (employer requirements, process engineering,
    hydraulic profile, equipment list) kept for the life of the project.
    ``transient``: RFQ-specific inputs (RFQ template, datasheets, specs) needed only
    during generation; deleted from storage once the RFQ has been generated.
    """

    PERSISTENT = "persistent"
    TRANSIENT = "transient"


class Document(Base):
    """An uploaded source document belonging to a project.

    The file bytes live in Supabase Storage at ``storage_path``; only short-lived
    signed URLs ever expose them. ``doc_type`` is a free-form string (not a DB
    enum) so the classification taxonomy can evolve without schema migrations.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    doc_type: Mapped[str | None] = mapped_column(String(64), index=True)
    doc_type_source: Mapped[DocTypeSource] = mapped_column(
        Enum(DocTypeSource, name="doc_type_source", values_callable=_enum_values),
        nullable=False,
        server_default=DocTypeSource.AUTO.value,
    )
    revision_label: Mapped[str | None] = mapped_column(String(32))
    revision_number: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    sheet_names: Mapped[list[str] | None] = mapped_column(JSONB)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=_enum_values),
        nullable=False,
        server_default=DocumentStatus.PENDING.value,
    )
    retention: Mapped[RetentionPolicy] = mapped_column(
        Enum(RetentionPolicy, name="retention_policy", values_callable=_enum_values),
        nullable=False,
        server_default=RetentionPolicy.TRANSIENT.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
