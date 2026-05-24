"""Upload (signed direct-to-storage), classify, and manage documents (owner-scoped)."""

import contextlib
import logging
import uuid
from collections.abc import Sequence
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from storage3 import AsyncStorageClient
from storage3.utils import StorageException

from app.api.deps import (
    current_user_id,
    get_db,
    get_storage,
    load_owned_document,
    load_owned_project,
)
from app.core.config import Settings, get_settings
from app.core.security import get_current_user
from app.models.document import DocTypeSource, Document, DocumentStatus
from app.schemas.document import (
    DocumentClassificationUpdate,
    DocumentDetail,
    DocumentInitRequest,
    DocumentInitResponse,
    DocumentRead,
)
from app.services.ingestion.classifier import classify_filename, retention_for
from app.services.ingestion.filetype import canonical_content_type
from app.services.ingestion.upload import (
    UploadValidationError,
    fetch_object_size,
    get_project_document_usage,
    plan_storage_path,
    purge_stale_pending_documents,
    run_document_validation,
    validate_upload_request,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["documents"])

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[AsyncStorageClient, Depends(get_storage)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_FALLBACK_CONTENT_TYPE = "application/octet-stream"


@router.post(
    "/projects/{project_id}/documents/init",
    response_model=DocumentInitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def init_document_upload(
    project_id: uuid.UUID,
    payload: DocumentInitRequest,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
) -> DocumentInitResponse:
    """Validate and classify a planned upload, then issue a signed direct-upload URL.

    Creates a ``pending`` document row; the client uploads the bytes straight to
    Supabase Storage using the returned URL/token, then calls ``finalize``.
    """
    owner_id = current_user_id(user)
    # Lock the project row so concurrent uploads serialize their quota checks below.
    project = await load_owned_project(db, project_id, owner_id, for_update=True)

    # Opportunistically clean up abandoned pending uploads (own txn; never blocks).
    await purge_stale_pending_documents(storage, project_id=project.id, settings=settings)

    count, total = await get_project_document_usage(db, project.id)
    try:
        ext = validate_upload_request(
            filename=payload.filename,
            declared_size=payload.size_bytes,
            existing_count=count,
            existing_total_bytes=total,
            settings=settings,
        )
    except UploadValidationError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    content_type = canonical_content_type(ext) or _FALLBACK_CONTENT_TYPE
    classification = classify_filename(payload.filename)
    document_id = uuid.uuid4()
    bucket = settings.SUPABASE_STORAGE_BUCKET
    storage_path = plan_storage_path(project.id, document_id, ext)

    document = Document(
        id=document_id,
        project_id=project.id,
        original_filename=payload.filename,
        storage_bucket=bucket,
        storage_path=storage_path,
        content_type=content_type,
        size_bytes=payload.size_bytes,
        doc_type=classification.doc_type,
        doc_type_source=DocTypeSource.AUTO,
        revision_label=classification.revision_label,
        revision_number=classification.revision_number,
        status=DocumentStatus.PENDING,
        retention=retention_for(classification.doc_type),
        uploaded_by=owner_id,
    )
    db.add(document)
    await db.flush()

    try:
        signed = await storage.from_(bucket).create_signed_upload_url(storage_path)
    except StorageException as exc:
        logger.warning("failed to create signed upload URL for %s: %s", storage_path, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not create upload URL") from exc

    await db.refresh(document)
    return DocumentInitResponse(
        document=DocumentRead.model_validate(document),
        upload_url=signed["signed_url"],
        token=signed["token"],
        storage_path=storage_path,
    )


async def _fail_finalize(
    db: AsyncSession, storage: AsyncStorageClient, document: Document, reason: str
) -> NoReturn:
    """Mark a finalizing document ``failed``, remove its object, and raise 413."""
    with contextlib.suppress(StorageException):
        await storage.from_(document.storage_bucket).remove([document.storage_path])
    document.status = DocumentStatus.FAILED
    document.failure_reason = reason
    await db.commit()  # persist the failure before signalling the client
    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, reason)


@router.post("/documents/{document_id}/finalize", response_model=DocumentRead)
async def finalize_document_upload(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
) -> Document:
    """Verify the uploaded object and kick off background content validation.

    Returns the document with ``status=processing``; the client polls until it is
    ``ready`` or ``failed``. An object that is missing yields 400 (retryable, the row
    stays ``pending``); an object that breaks the per-file or project-total size cap
    yields 413 and is marked ``failed`` (re-checking the actual size here closes the
    gap where a client under-declared its size at init).
    """
    owner_id = current_user_id(user)
    document = await load_owned_document(db, document_id, owner_id)
    if document.status != DocumentStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is not awaiting finalization")

    try:
        actual_size = await fetch_object_size(
            storage, bucket=document.storage_bucket, storage_path=document.storage_path
        )
    except StorageException as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Uploaded object not found in storage"
        ) from exc

    max_file = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if actual_size is not None and actual_size > max_file:
        await _fail_finalize(db, storage, document, "Uploaded object exceeds the size limit")

    if actual_size is not None:
        # Re-check the project total against the *actual* size (init only saw the
        # declared size). The authoritative quota lock is held at init; this is a
        # single-instance backstop, so no extra row lock is taken here.
        max_total = settings.MAX_PROJECT_TOTAL_SIZE_MB * 1024 * 1024
        _, other_total = await get_project_document_usage(
            db, document.project_id, exclude_document_id=document.id
        )
        if other_total + actual_size > max_total:
            await _fail_finalize(
                db, storage, document, "Upload would exceed the project size limit"
            )
        document.size_bytes = actual_size
    document.status = DocumentStatus.PROCESSING
    # Commit before scheduling so the background task's own session sees `processing`
    # (it runs in-process right after the response).
    await db.commit()
    await db.refresh(document)

    background_tasks.add_task(run_document_validation, storage, document.id)
    return document


@router.get("/projects/{project_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Sequence[Document]:
    """List a project's documents (with classification + status), newest first."""
    await load_owned_project(db, project_id, current_user_id(user))
    stmt = (
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
) -> DocumentDetail:
    """Fetch document metadata plus a short-lived signed download URL (404 if not owned)."""
    document = await load_owned_document(db, document_id, current_user_id(user))
    download_url = ""
    # Only ready/processing documents have stored bytes to sign for; pending has no
    # upload yet and failed has had its object removed. If signing fails for a document
    # that should have bytes, surface it (502) rather than returning an empty URL.
    if document.status in (DocumentStatus.READY, DocumentStatus.PROCESSING):
        try:
            signed = await storage.from_(document.storage_bucket).create_signed_url(
                document.storage_path, settings.SIGNED_DOWNLOAD_URL_TTL_S
            )
        except StorageException as exc:
            logger.warning("failed to create download URL for %s: %s", document_id, exc)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Could not create download URL"
            ) from exc
        download_url = signed["signedURL"]
    base = DocumentRead.model_validate(document)
    return DocumentDetail(**base.model_dump(), download_url=download_url)


@router.patch("/documents/{document_id}", response_model=DocumentRead)
async def update_document_classification(
    document_id: uuid.UUID, payload: DocumentClassificationUpdate, user: CurrentUser, db: DbSession
) -> Document:
    """Override a document's classification (marks the source as manual)."""
    document = await load_owned_document(db, document_id, current_user_id(user))
    document.doc_type = payload.doc_type.value
    document.doc_type_source = DocTypeSource.MANUAL
    document.retention = retention_for(payload.doc_type.value)
    await db.flush()
    await db.refresh(document)
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: Storage
) -> None:
    """Delete a document row and best-effort remove its storage object."""
    document = await load_owned_document(db, document_id, current_user_id(user))
    bucket, path = document.storage_bucket, document.storage_path
    await db.delete(document)
    await db.flush()
    try:
        await storage.from_(bucket).remove([path])
    except StorageException as exc:
        # The row is gone but the object lingers; log so the orphan is observable.
        logger.warning("failed to remove storage object %s/%s on delete: %s", bucket, path, exc)
