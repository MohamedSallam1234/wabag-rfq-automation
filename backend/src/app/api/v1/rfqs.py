"""Generate a populated RFQ datasheet for one equipment from a project's documents (open)."""

import logging
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from storage3 import AsyncStorageClient
from storage3.utils import StorageException

from app.agents.llm.router import LLMFatalError, LLMRouter, LLMTransientError
from app.api.deps import get_db, get_router, get_storage, load_project_or_404
from app.core.config import Settings, get_settings
from app.models.document import DocTypeSource, Document, RetentionPolicy
from app.schemas.document import DocumentRead
from app.schemas.rfq import RFQGenerationResponse
from app.services.ingestion.filetype import canonical_content_type, normalize_extension
from app.services.ingestion.validation import (
    UploadValidationError,
    plan_storage_path,
    validate_upload_bytes,
)
from app.services.rfq.generator import RFQGenerationError, generate_rfq, summarize

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["rfqs"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[AsyncStorageClient, Depends(get_storage)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Llm = Annotated[LLMRouter, Depends(get_router)]

#: ``doc_type`` stamped on generated RFQ outputs (also used to exclude them from source context).
GENERATED_DOC_TYPE = "RFQ Package"
_XLSX_FALLBACK_MIME = "application/octet-stream"


def _slug(text: str) -> str:
    """Slugify a name into a filesystem/key-safe stem (alphanumerics + underscores)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_") or "equipment"


@router.post(
    "/projects/{project_id}/rfqs",
    status_code=status.HTTP_201_CREATED,
    response_model=RFQGenerationResponse,
)
async def generate_project_rfq(  # noqa: PLR0915
    project_id: uuid.UUID,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
    llm: Llm,
    file: Annotated[UploadFile, File()],
    equipment: Annotated[str, Form(min_length=1)],
) -> RFQGenerationResponse:
    """Generate an RFQ datasheet for ``equipment`` from the project's documents(multiple LLM calls).

    The client POSTs the RFQ template (multipart ``file``) plus the ``equipment`` name. The template
    is validated and converted to Markdown in-memory (never stored); every project source document's
    stored Markdown is downloaded; Multiple LLM calls for data extraction and one final LLM call
    for merging and filling the JSON result (MapReduce approach); the JSON result is rendered
    to a fresh ``.xlsx``, stored, and persisted as a ``documents`` row. Errors: 415 (bad template
    type), 422 (unparseable template / no source documents), 502 (LLM produced invalid JSON or a
    storage op failed), 503 (LLM unavailable), 404 (project missing).
    """
    project = await load_project_or_404(db, project_id)

    # Convert the uploaded template to Markdown in-memory (reuse the intake pipeline); not stored.
    template_filename = file.filename or ""
    ext = normalize_extension(template_filename)
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_UPLOAD_EXTENSIONS)
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported template type '{ext or template_filename}'; allowed: {allowed}",
        )
    try:
        validated = await validate_upload_bytes(file, ext=ext, settings=settings)
    except UploadValidationError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    template_md = validated.data.decode("utf-8")
    template_label = f"{template_filename} (RFQ Template)"

    # Source context = every project document except previously-generated RFQ outputs.
    stmt = select(Document).where(
        Document.project_id == project_id,
        or_(Document.doc_type.is_(None), Document.doc_type != GENERATED_DOC_TYPE),
    )
    sources = (await db.execute(stmt)).scalars().all()
    if not sources:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Project has no source documents to generate from",
        )

    bucket = settings.SUPABASE_STORAGE_BUCKET
    try:
        generation, xlsx_bytes = await generate_rfq(
            equipment=equipment,
            template_label=template_label,
            template_md=template_md,
            sources=sources,
            storage=storage,
            bucket=bucket,
            llm=llm,
            max_concurrency=settings.RFQ_MAX_CONCURRENT_EXTRACTIONS,
        )
    except LLMTransientError as exc:
        logger.warning("RFQ generation LLM unavailable: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM is unavailable") from exc
    except LLMFatalError as exc:
        logger.warning("RFQ generation LLM fatal error: %s", exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "LLM rejected the request") from exc
    except RFQGenerationError as exc:
        logger.warning("RFQ generation produced unusable output: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The model returned an invalid RFQ"
        ) from exc
    except StorageException as exc:
        logger.warning("RFQ generation could not read a source document: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Could not read a source document"
        ) from exc

    document_id = uuid.uuid4()
    stem = _slug(equipment)
    xlsx_mime = canonical_content_type(".xlsx") or _XLSX_FALLBACK_MIME
    storage_path = plan_storage_path(project.id, document_id, f"RFQ_{stem}", ".xlsx")
    try:
        await storage.from_(bucket).upload(storage_path, xlsx_bytes, {"content-type": xlsx_mime})
    except StorageException as exc:
        logger.warning("failed to store generated RFQ %s: %s", storage_path, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Could not store the generated RFQ"
        ) from exc

    document = Document(
        id=document_id,
        project_id=project.id,
        original_filename=f"RFQ_{stem}.xlsx",
        storage_bucket=bucket,
        storage_path=storage_path,
        content_type=xlsx_mime,
        size_bytes=len(xlsx_bytes),
        page_count=None,
        sheet_names=None,
        doc_type=GENERATED_DOC_TYPE,
        doc_type_source=DocTypeSource.AUTO,
        retention=RetentionPolicy.PERSISTENT,
    )
    db.add(document)
    try:
        await db.flush()
        await db.refresh(document)
    except Exception:
        # The object is uploaded but the row failed to persist; remove the orphan so
        # storage and DB stay consistent (best-effort — log if cleanup also fails).
        try:
            await storage.from_(bucket).remove([storage_path])
        except StorageException as cleanup_exc:
            logger.warning(
                "failed to remove orphaned RFQ object %s/%s after persist failure: %s",
                bucket,
                storage_path,
                cleanup_exc,
            )
        raise
    return RFQGenerationResponse(
        document=DocumentRead.model_validate(document), summary=summarize(generation)
    )
