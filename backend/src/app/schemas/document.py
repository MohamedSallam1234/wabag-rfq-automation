"""Pydantic request/response schemas for documents."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocTypeSource, RetentionPolicy
from app.services.ingestion.classifier import DocType


class DocumentRead(BaseModel):
    """Document metadata as returned by the API (storage location is never exposed)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int | None
    doc_type: str | None
    doc_type_source: DocTypeSource
    revision_label: str | None
    revision_number: int | None
    page_count: int | None
    sheet_names: list[str] | None
    retention: RetentionPolicy
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentRead):
    """A document plus a short-lived signed download URL."""

    download_url: str


class DocumentClassificationUpdate(BaseModel):
    """Payload to override a document's classification (validated against known types)."""

    doc_type: DocType
