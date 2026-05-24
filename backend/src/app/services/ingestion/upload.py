"""Upload orchestration: request validation, storage paths, and background validation.

The byte transfer happens directly between the client and Supabase Storage (signed
URLs), so the backend never buffers an upload. The only server-side read is the
background validation step, which streams the stored object to a temp file on disk
(RAM-bounded) and deep-parses it off the event loop to reject corrupt/mismatched
files.
"""

import contextlib
import functools
import hashlib
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from storage3 import AsyncStorageClient
from storage3.utils import StorageException

from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionLocal
from app.models.document import Document, DocumentStatus
from app.services.ingestion.antivirus import scan_file
from app.services.ingestion.archive import ZipBombError, assert_zip_within_limits
from app.services.ingestion.excel_parser import extract_xlsx_sheet_names
from app.services.ingestion.filetype import (
    SNIFF_LENGTH,
    magic_matches_extension,
    normalize_extension,
)
from app.services.ingestion.pdf_parser import extract_pdf_page_count
from app.services.ingestion.word_parser import validate_docx

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024


class UploadValidationError(Exception):
    """An upload request failed validation; carries the HTTP status to surface."""

    def __init__(self, status_code: int, detail: str) -> None:
        """Store the HTTP ``status_code`` and human-readable ``detail``."""
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class _ParseError(Exception):
    """Internal marker: a downloaded file could not be parsed as its declared type."""


@dataclass(frozen=True)
class ValidationOutcome:
    """Result of validating a stored object during background processing.

    ``ok=False`` with ``transient=True`` marks a *retryable* infrastructure failure
    (e.g. a storage download blip): the document is left ``processing`` and its bytes
    are kept, to be retried by :func:`recover_stuck_processing_documents`. ``ok=False``
    with ``transient=False`` is a *permanent* content failure (wrong type / unparseable)
    that fails the document and removes the object.
    """

    ok: bool
    failure_reason: str | None
    page_count: int | None
    sheet_names: list[str] | None
    sha256: str | None
    size_bytes: int | None
    transient: bool = False


@dataclass(frozen=True)
class DownloadedObject:
    """A stored object streamed to a local temp file. The caller must delete ``path``."""

    path: str
    size_bytes: int
    head: bytes
    sha256: str | None


def plan_storage_path(project_id: uuid.UUID, document_id: uuid.UUID, ext: str) -> str:
    """Build the storage object key for a document: ``{project_id}/{document_id}{ext}``."""
    return f"{project_id}/{document_id}{ext}"


def validate_upload_request(
    *,
    filename: str,
    declared_size: int,
    existing_count: int,
    existing_total_bytes: int,
    settings: Settings,
) -> str:
    """Validate a requested upload against the extension allowlist and the size/count caps.

    Args:
        filename: The original filename (used for its extension).
        declared_size: The client-declared file size in bytes.
        existing_count: Number of non-failed documents already in the project.
        existing_total_bytes: Sum of sizes of those documents.
        settings: Application settings holding the caps.

    Returns:
        The normalized (lowercase, dot-prefixed) file extension.

    Raises:
        UploadValidationError: 415 (bad extension), 413 (file/project too large),
            or 409 (too many files).
    """
    ext = normalize_extension(filename)
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_UPLOAD_EXTENSIONS)
        raise UploadValidationError(
            415, f"Unsupported file type '{ext or filename}'; allowed: {allowed}"
        )

    max_file = settings.MAX_UPLOAD_SIZE_MB * _BYTES_PER_MB
    if declared_size <= 0 or declared_size > max_file:
        raise UploadValidationError(
            413,
            f"File size {declared_size} bytes is invalid or exceeds "
            f"the {settings.MAX_UPLOAD_SIZE_MB} MB limit",
        )

    if existing_count >= settings.MAX_FILES_PER_PROJECT:
        raise UploadValidationError(
            409, f"Project already has the maximum of {settings.MAX_FILES_PER_PROJECT} documents"
        )

    max_total = settings.MAX_PROJECT_TOTAL_SIZE_MB * _BYTES_PER_MB
    if existing_total_bytes + declared_size > max_total:
        raise UploadValidationError(
            413,
            f"Upload would exceed the project size limit "
            f"of {settings.MAX_PROJECT_TOTAL_SIZE_MB} MB",
        )

    return ext


async def get_project_document_usage(
    db: AsyncSession, project_id: uuid.UUID, *, exclude_document_id: uuid.UUID | None = None
) -> tuple[int, int]:
    """Return ``(count, total_size_bytes)`` of non-failed documents in a project.

    ``exclude_document_id`` omits one document from the totals — used at finalize to
    measure usage *excluding* the document being finalized (whose row already carries
    the client-declared size, which the actual size will replace).
    """
    stmt = select(
        func.count(Document.id),
        func.coalesce(func.sum(Document.size_bytes), 0),
    ).where(
        Document.project_id == project_id,
        Document.status != DocumentStatus.FAILED,
    )
    if exclude_document_id is not None:
        stmt = stmt.where(Document.id != exclude_document_id)
    count, total = (await db.execute(stmt)).one()
    return int(count), int(total)


async def fetch_object_size(
    storage: AsyncStorageClient, *, bucket: str, storage_path: str
) -> int | None:
    """Return the actual size of a stored object, or raise if it does not exist.

    Raises:
        StorageException: If the object cannot be found / inspected.
    """
    info = await storage.from_(bucket).info(storage_path)
    return _extract_size(info)


def _extract_size(info: dict[str, Any]) -> int | None:
    """Pull a byte size out of a Supabase ``info`` payload, tolerating shape changes."""
    for key in ("size", "contentLength"):
        value = info.get(key)
        if isinstance(value, int):
            return value
    metadata = info.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("size")
        if isinstance(value, int):
            return value
    return None


async def _download_to_file(
    url: str, tmp_path: str, settings: Settings
) -> tuple[bytes, int, str | None]:
    """Stream a signed-URL download to ``tmp_path``; return (head bytes, size, sha256)."""
    head = b""
    size = 0
    # sha256 is stored on the document for future content dedup / integrity; it has no
    # consumer yet, so COMPUTE_SHA256 can be disabled to skip the hashing cost.
    hasher = hashlib.sha256() if settings.COMPUTE_SHA256 else None
    async with (
        httpx.AsyncClient(
            timeout=settings.STORAGE_CLIENT_TIMEOUT_S, follow_redirects=True
        ) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        with open(tmp_path, "wb") as buffer:
            async for chunk in response.aiter_bytes(settings.DOWNLOAD_CHUNK_SIZE):
                if len(head) < SNIFF_LENGTH:
                    head += chunk[: SNIFF_LENGTH - len(head)]
                size += len(chunk)
                if hasher is not None:
                    hasher.update(chunk)
                buffer.write(chunk)
    return head, size, (hasher.hexdigest() if hasher is not None else None)


async def download_object_to_tempfile(
    storage: AsyncStorageClient,
    *,
    bucket: str,
    storage_path: str,
    settings: Settings,
    suffix: str = "",
) -> DownloadedObject:
    """Stream a stored object to a temp file on disk (RAM-bounded) via a signed URL.

    The whole object is fetched — document formats (PDF/OOXML) can't be parsed from a
    byte range — but only ~one chunk is held in memory at a time. The caller owns the
    returned temp file and must delete ``DownloadedObject.path``.

    Raises:
        StorageException: If a signed URL cannot be created.
        httpx.HTTPError: If the download itself fails.
    """
    signed = await storage.from_(bucket).create_signed_url(
        storage_path, settings.SIGNED_DOWNLOAD_URL_TTL_S
    )
    url = signed["signedURL"]
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        head, size, sha = await _download_to_file(url, tmp_path, settings)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    return DownloadedObject(path=tmp_path, size_bytes=size, head=head, sha256=sha)


async def _assert_archive_safe(tmp_path: str, settings: Settings) -> None:
    """Reject OOXML decompression bombs before parsing (raises :class:`_ParseError`)."""
    check = functools.partial(
        assert_zip_within_limits,
        tmp_path,
        max_uncompressed_bytes=settings.MAX_DECOMPRESSED_SIZE_MB * _BYTES_PER_MB,
        max_ratio=settings.MAX_COMPRESSION_RATIO,
        max_entries=settings.MAX_ARCHIVE_ENTRIES,
    )
    try:
        await anyio.to_thread.run_sync(check)
    except ZipBombError as exc:
        raise _ParseError(str(exc)) from exc


async def _deep_parse(
    tmp_path: str, ext: str, settings: Settings
) -> tuple[int | None, list[str] | None]:
    """Parse the downloaded file off the event loop; return (page_count, sheet_names).

    OOXML files (.xlsx/.docx) are first checked against the decompression-bomb caps
    (cheap central-directory inspection) before they are handed to a parser.

    Raises:
        _ParseError: If the file cannot be parsed as its declared type, or trips the
            archive-safety limits.
    """
    try:
        if ext == ".pdf":
            return await anyio.to_thread.run_sync(extract_pdf_page_count, tmp_path), None
        if ext == ".xlsx":
            await _assert_archive_safe(tmp_path, settings)
            return None, await anyio.to_thread.run_sync(extract_xlsx_sheet_names, tmp_path)
        if ext == ".docx":
            await _assert_archive_safe(tmp_path, settings)
            await anyio.to_thread.run_sync(validate_docx, tmp_path)
            return None, None
    except _ParseError:
        raise  # already a clear, permanent failure (bad parse or zip bomb)
    except Exception as exc:
        raise _ParseError(f"File could not be parsed as {ext}: {exc}") from exc
    return None, None  # .xls: accepted as a stored blob (no parser available)


async def _download_with_retries(
    storage: AsyncStorageClient,
    *,
    bucket: str,
    storage_path: str,
    ext: str,
    settings: Settings,
) -> DownloadedObject:
    """Download the object, retrying transient ``httpx`` errors with linear backoff.

    Raises:
        httpx.HTTPError: If every attempt fails (treated as a transient failure upstream).
    """
    attempts = max(1, settings.VALIDATION_MAX_ATTEMPTS)
    last_exc: httpx.HTTPError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await download_object_to_tempfile(
                storage, bucket=bucket, storage_path=storage_path, settings=settings, suffix=ext
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < attempts:
                logger.warning(
                    "validation download attempt %d/%d failed for %s: %s",
                    attempt,
                    attempts,
                    storage_path,
                    exc,
                )
                await anyio.sleep(settings.VALIDATION_RETRY_BACKOFF_S * attempt)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("download retry loop did not execute")  # pragma: no cover


async def validate_stored_object(
    storage: AsyncStorageClient,
    *,
    bucket: str,
    storage_path: str,
    ext: str,
    settings: Settings,
) -> ValidationOutcome:
    """Download a stored object and validate its magic bytes and parseability.

    Streams the object to a temp file (RAM-bounded), checks the magic bytes against
    the extension, then deep-parses it. The temp file is always removed. A download
    failure is reported as ``transient`` (retryable) rather than a permanent failure.
    """
    try:
        downloaded = await _download_with_retries(
            storage, bucket=bucket, storage_path=storage_path, ext=ext, settings=settings
        )
    except httpx.HTTPError as exc:
        return ValidationOutcome(
            ok=False,
            transient=True,
            failure_reason=f"Could not download object for validation: {exc}"[:255],
            page_count=None,
            sheet_names=None,
            sha256=None,
            size_bytes=None,
        )
    try:
        if not magic_matches_extension(downloaded.head, ext):
            return ValidationOutcome(
                ok=False,
                failure_reason=f"File content is not a valid {ext} file",
                page_count=None,
                sheet_names=None,
                sha256=None,
                size_bytes=downloaded.size_bytes,
            )
        scan = await scan_file(downloaded.path, settings)
        if scan.error is not None:
            # Scanner unreachable/failed: fail closed — never accept an unscanned file.
            return ValidationOutcome(
                ok=False,
                transient=True,
                failure_reason=f"Antivirus scan unavailable: {scan.error}"[:255],
                page_count=None,
                sheet_names=None,
                sha256=None,
                size_bytes=downloaded.size_bytes,
            )
        if not scan.clean:
            return ValidationOutcome(
                ok=False,
                failure_reason=f"Malware detected: {scan.signature}"[:255],
                page_count=None,
                sheet_names=None,
                sha256=None,
                size_bytes=downloaded.size_bytes,
            )
        try:
            page_count, sheet_names = await _deep_parse(downloaded.path, ext, settings)
        except _ParseError as exc:
            return ValidationOutcome(
                ok=False,
                failure_reason=str(exc)[:255],
                page_count=None,
                sheet_names=None,
                sha256=None,
                size_bytes=downloaded.size_bytes,
            )
        return ValidationOutcome(
            ok=True,
            failure_reason=None,
            page_count=page_count,
            sheet_names=sheet_names,
            sha256=downloaded.sha256,
            size_bytes=downloaded.size_bytes,
        )
    finally:
        with contextlib.suppress(OSError):
            os.unlink(downloaded.path)


async def run_document_validation(storage: AsyncStorageClient, document_id: uuid.UUID) -> None:
    """Background entrypoint: validate a processing document and persist the outcome.

    On success the document becomes ``ready`` with extracted metadata; on failure it
    becomes ``failed`` and its storage object is removed. Opens its own DB session
    because the request session is already closed by the time this runs.
    """
    settings = get_settings()
    try:
        async with AsyncSessionLocal() as session:
            document = await session.get(Document, document_id)
            if document is None or document.status != DocumentStatus.PROCESSING:
                return
            logger.info("validating document %s", document_id)
            ext = normalize_extension(document.original_filename)
            try:
                outcome = await validate_stored_object(
                    storage,
                    bucket=document.storage_bucket,
                    storage_path=document.storage_path,
                    ext=ext,
                    settings=settings,
                )
            except StorageException as exc:
                # Storage-layer error (e.g. signed-URL creation) is transient: retry later.
                outcome = ValidationOutcome(
                    ok=False,
                    transient=True,
                    failure_reason=f"Storage error during validation: {exc}"[:255],
                    page_count=None,
                    sheet_names=None,
                    sha256=None,
                    size_bytes=None,
                )
            if outcome.ok:
                document.status = DocumentStatus.READY
                document.page_count = outcome.page_count
                document.sheet_names = outcome.sheet_names
                document.sha256 = outcome.sha256
                if outcome.size_bytes is not None:
                    document.size_bytes = outcome.size_bytes
                document.failure_reason = None
                await session.commit()
                logger.info("document %s ready (pages=%s)", document_id, outcome.page_count)
            elif outcome.transient:
                # Retryable infra failure: leave the row `processing` and keep the bytes;
                # `recover_stuck_processing_documents` will re-drive it later. No commit.
                logger.warning(
                    "transient validation failure for %s; left processing for retry: %s",
                    document_id,
                    outcome.failure_reason,
                )
            else:
                document.status = DocumentStatus.FAILED
                document.failure_reason = outcome.failure_reason or "validation failed"
                with contextlib.suppress(StorageException):
                    await storage.from_(document.storage_bucket).remove([document.storage_path])
                await session.commit()
                logger.info("document %s failed: %s", document_id, document.failure_reason)
    except Exception:
        logger.exception("document validation failed unexpectedly for %s", document_id)


async def purge_stale_pending_documents(
    storage: AsyncStorageClient, *, project_id: uuid.UUID, settings: Settings
) -> None:
    """Delete ``pending`` documents older than the TTL and remove any uploaded objects.

    Runs in its own session/transaction so it can never poison or block the caller's
    request; all errors are logged and swallowed.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.PENDING_UPLOAD_TTL_MIN)
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Document).where(
                Document.project_id == project_id,
                Document.status == DocumentStatus.PENDING,
                Document.created_at < cutoff,
            )
            stale = (await session.execute(stmt)).scalars().all()
            for document in stale:
                with contextlib.suppress(StorageException):
                    await storage.from_(document.storage_bucket).remove([document.storage_path])
                await session.delete(document)
            await session.commit()
    except Exception:
        logger.exception("failed to purge stale pending documents for project %s", project_id)


async def recover_stuck_processing_documents(
    storage: AsyncStorageClient, *, settings: Settings
) -> None:
    """Re-drive validation for documents stuck in ``processing`` past the recovery TTL.

    Covers two cases that would otherwise orphan a document forever: a process that
    crashed/restarted mid-validation, and a transient validation failure that was
    deliberately left in ``processing`` for retry. Intended to run at startup; opens
    its own session and swallows all errors so it can never block boot.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.PROCESSING_RECOVERY_TTL_MIN)
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Document.id).where(
                Document.status == DocumentStatus.PROCESSING,
                Document.updated_at < cutoff,
            )
            doc_ids = list((await session.execute(stmt)).scalars().all())
    except Exception:
        logger.exception("failed to query stuck processing documents")
        return
    if not doc_ids:
        return
    logger.info("recovering %d stuck processing document(s)", len(doc_ids))
    for doc_id in doc_ids:
        try:
            await run_document_validation(storage, doc_id)
        except Exception:
            logger.exception("failed to recover processing document %s", doc_id)


async def run_recovery_loop(storage: AsyncStorageClient, *, settings: Settings) -> None:
    """Periodically re-drive stuck ``processing`` documents until cancelled.

    Sweeps immediately, then every ``RECOVERY_SWEEP_INTERVAL_S`` seconds. This is what
    turns a steady-state transient failure (left ``processing`` for retry) into an
    eventual resolution instead of waiting for the next restart. Each sweep's errors
    are swallowed so the loop never dies; cancellation on app shutdown breaks out
    cleanly via the cancellable ``anyio.sleep``.
    """
    while True:
        try:
            await recover_stuck_processing_documents(storage, settings=settings)
        except Exception:
            logger.exception("recovery sweep failed")
        await anyio.sleep(settings.RECOVERY_SWEEP_INTERVAL_S)
