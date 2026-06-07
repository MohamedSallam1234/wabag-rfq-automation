"""Upload, classify, and manage documents (open endpoints — no authentication)."""

import logging
import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storage3 import AsyncStorageClient
from storage3.utils import StorageException

from app.api.deps import get_db, get_storage, load_document_or_404, load_project_or_404
from app.core.config import Settings, get_settings
from app.models.document import DocTypeSource, Document
from app.schemas.document import (
    DocumentClassificationUpdate,
    DocumentDetail,
    DocumentRead,
)
from app.services.ingestion.classifier import classify_filename, retention_for
from app.services.ingestion.filetype import normalize_extension
from app.services.ingestion.validation import (
    UploadValidationError,
    plan_storage_path,
    validate_upload_bytes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["documents"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[AsyncStorageClient, Depends(get_storage)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post(
    "/projects/{project_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentRead,
)
async def upload_document(
    project_id: uuid.UUID,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
    file: Annotated[UploadFile, File()],
) -> Document:
    """Upload a document: validate its bytes, store them, classify it, and persist the row.

    A single synchronous step. The client POSTs the file; the backend validates the
    extension and content (magic bytes + deep parse), uploads the validated bytes to
    Supabase Storage, classifies the filename, and returns the created document. Born-digital
    PDFs are slimmed to a Markdown artifact (text + tables) and stored as ``.md`` — the heavy
    original is discarded. Invalid files are rejected (415 / 422 / 413) and nothing is stored.
    """
    filename = file.filename or ""
    ext = normalize_extension(filename)
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_UPLOAD_EXTENSIONS)
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported file type '{ext or filename}'; allowed: {allowed}",
        )

    project = await load_project_or_404(db, project_id)

    try:
        validated = await validate_upload_bytes(file, ext=ext, settings=settings)
    except UploadValidationError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    # Classification runs on the original filename (e.g. the ``*.pdf`` name), not the stored
    # ``.md`` object, so the prefix and *DataSheet*/*Specs* rules still fire.
    classification = classify_filename(filename)
    document_id = uuid.uuid4()
    bucket = settings.SUPABASE_STORAGE_BUCKET
    storage_path = plan_storage_path(project.id, document_id, validated.stored_ext)

    # Store the validated bytes first; only persist the row if the upload succeeds (a row
    # with no object would be unusable). The reverse gap — a DB failure after a successful
    # upload — leaves a rare orphan object, an accepted simplification.
    try:
        await storage.from_(bucket).upload(
            storage_path, validated.data, {"content-type": validated.content_type}
        )
    except StorageException as exc:
        logger.warning("failed to store object %s: %s", storage_path, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Could not store the uploaded file"
        ) from exc

    document = Document(
        id=document_id,
        project_id=project.id,
        original_filename=filename,
        storage_bucket=bucket,
        storage_path=storage_path,
        content_type=validated.content_type,
        size_bytes=validated.size_bytes,
        page_count=validated.page_count,
        sheet_names=validated.sheet_names,
        doc_type=classification.doc_type,
        doc_type_source=DocTypeSource.AUTO,
        revision_label=classification.revision_label,
        revision_number=classification.revision_number,
        retention=retention_for(classification.doc_type),
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)
    return document


@router.get("/projects/{project_id}/documents", response_model=list[DocumentRead])
async def list_documents(project_id: uuid.UUID, db: DbSession) -> Sequence[Document]:
    """List a project's documents (with classification), newest first."""
    await load_project_or_404(db, project_id)
    stmt = (
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.get("/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
) -> DocumentDetail:
    """Fetch document metadata plus a short-lived signed download URL (404 if missing)."""
    document = await load_document_or_404(db, document_id)
    try:
        signed = await storage.from_(document.storage_bucket).create_signed_url(
            document.storage_path, settings.SIGNED_DOWNLOAD_URL_TTL_S
        )
    except StorageException as exc:
        logger.warning("failed to create download URL for %s: %s", document_id, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not create download URL") from exc
    download_url = signed["signedURL"]
    if not download_url:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not create download URL")
    base = DocumentRead.model_validate(document)
    return DocumentDetail(**base.model_dump(), download_url=download_url)


@router.patch("/documents/{document_id}", response_model=DocumentRead)
async def update_document_classification(
    document_id: uuid.UUID, payload: DocumentClassificationUpdate, db: DbSession
) -> Document:
    """Override a document's classification (marks the source as manual)."""
    document = await load_document_or_404(db, document_id)
    document.doc_type = payload.doc_type.value
    document.doc_type_source = DocTypeSource.MANUAL
    document.retention = retention_for(payload.doc_type.value)
    await db.flush()
    await db.refresh(document)
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, db: DbSession, storage: Storage) -> None:
    """Delete a document row and best-effort remove its storage object."""
    document = await load_document_or_404(db, document_id)
    bucket, path = document.storage_bucket, document.storage_path
    await db.delete(document)
    await db.flush()
    try:
        await storage.from_(bucket).remove([path])
    except StorageException as exc:
        # The row is gone but the object lingers; log so the orphan is observable.
        logger.warning("failed to remove storage object %s/%s on delete: %s", bucket, path, exc)
