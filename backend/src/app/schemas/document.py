"""Pydantic request/response schemas for documents."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocTypeSource, DocumentStatus, RetentionPolicy
from app.services.ingestion.classifier import DocType


class DocumentInitRequest(BaseModel):
    """Payload to begin a direct-to-storage upload."""

    filename: str = Field(min_length=1, max_length=512)
    content_type: str | None = Field(default=None, max_length=128)
    size_bytes: int = Field(gt=0, description="Client-declared file size in bytes")


class DocumentRead(BaseModel):
    """Document metadata as returned by the API (storage location is never exposed)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int | None
    sha256: str | None
    doc_type: str | None
    doc_type_source: DocTypeSource
    revision_label: str | None
    revision_number: int | None
    page_count: int | None
    sheet_names: list[str] | None
    status: DocumentStatus
    retention: RetentionPolicy
    failure_reason: str | None
    uploaded_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DocumentInitResponse(BaseModel):
    """Response to an upload-init call: the pending document plus where to PUT the bytes."""

    document: DocumentRead
    upload_url: str
    token: str
    storage_path: str


class DocumentDetail(DocumentRead):
    """A document plus a short-lived signed download URL."""

    download_url: str


class DocumentClassificationUpdate(BaseModel):
    """Payload to override a document's classification (validated against known types)."""

    doc_type: DocType
