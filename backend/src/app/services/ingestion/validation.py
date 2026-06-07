"""Synchronous upload validation: size guard, magic-byte check, deep parse, and PDF slimming.

The client POSTs the file bytes to the backend, which streams them to a temp file on disk
(RAM-bounded), checks the magic bytes against the extension, and deep-parses the file to reject
corrupt or mismatched content. Born-digital PDFs are additionally converted to a compact
Markdown artifact (text + tables) and only that slim version is stored — the heavy original is
discarded. Only files that pass are uploaded to storage; an invalid file is a synchronous 4xx
and nothing is ever stored.

Two size caps apply: the *incoming body* cap (``MAX_UPLOAD_SIZE_MB``) can be large because the
original PDF is discarded, while the *stored artifact* cap (``MAX_STORED_ARTIFACT_MB``) matches
the Supabase bucket ``file_size_limit`` and is checked against the final stored bytes.
"""

import contextlib
import os
import tempfile
import uuid
from dataclasses import dataclass

import anyio
from fastapi import UploadFile

from app.core.config import Settings
from app.services.ingestion.excel_parser import extract_xlsx_sheet_names
from app.services.ingestion.filetype import (
    SNIFF_LENGTH,
    canonical_content_type,
    magic_matches_extension,
)
from app.services.ingestion.pdf_text import NoExtractableTextError, extract_pdf_markdown
from app.services.ingestion.word_parser import validate_docx

_BYTES_PER_MB = 1024 * 1024
_READ_CHUNK_SIZE = 1024 * 1024
_FALLBACK_CONTENT_TYPE = "application/octet-stream"
_MARKDOWN_CONTENT_TYPE = "text/markdown"


class UploadValidationError(Exception):
    """An upload failed validation; carries the HTTP status to surface to the client."""

    def __init__(self, status_code: int, detail: str) -> None:
        """Store the HTTP ``status_code`` and human-readable ``detail``."""
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class ValidatedUpload:
    """The validated bytes to store plus the metadata extracted while parsing.

    ``data``/``size_bytes`` describe the *stored* artifact: for a PDF that is the extracted
    Markdown (``stored_ext=".md"``, ``content_type="text/markdown"``); for other types it is
    the original bytes stored as-is.
    """

    data: bytes
    size_bytes: int
    page_count: int | None
    sheet_names: list[str] | None
    stored_ext: str
    content_type: str


def plan_storage_path(project_id: uuid.UUID, document_id: uuid.UUID, ext: str) -> str:
    """Build the storage object key for a document: ``{project_id}/{document_id}{ext}``."""
    return f"{project_id}/{document_id}{ext}"


async def _parse_office_metadata(tmp_path: str, ext: str) -> tuple[int | None, list[str] | None]:
    """Parse a non-PDF office file off the event loop; return ``(page_count, sheet_names)``.

    Opening the file with the format's parser is the integrity check: a corrupt file, or one
    whose real type does not match its extension (e.g. an ``.xlsx`` renamed ``.docx``), fails
    to parse. ``.xls`` has no parser and is accepted as a stored blob.

    Raises:
        UploadValidationError: 422 if the file cannot be parsed as its declared type.
    """
    try:
        if ext == ".xlsx":
            return None, await anyio.to_thread.run_sync(extract_xlsx_sheet_names, tmp_path)
        if ext == ".docx":
            await anyio.to_thread.run_sync(validate_docx, tmp_path)
            return None, None
    except Exception as exc:
        raise UploadValidationError(422, f"File could not be parsed as {ext}: {exc}") from exc
    return None, None  # .xls: accepted as a stored blob (no parser available)


async def _slim_pdf(tmp_path: str) -> tuple[bytes, int]:
    """Convert a born-digital PDF to Markdown bytes off the event loop; return ``(data, pages)``.

    Raises:
        UploadValidationError: 422 if the PDF has no extractable text (scanned / image-only)
            or otherwise cannot be parsed (e.g. encrypted).
    """
    try:
        markdown, page_count = await anyio.to_thread.run_sync(extract_pdf_markdown, tmp_path)
    except NoExtractableTextError as exc:
        raise UploadValidationError(
            422,
            "This PDF has no extractable text layer — it appears to be image-only (e.g. created "
            "by 'Microsoft Print to PDF', scanned, or with text saved as images/outlines). "
            "Upload a text-based PDF or the original source file (e.g. the Word/Excel document).",
        ) from exc
    except Exception as exc:
        raise UploadValidationError(422, f"File could not be parsed as .pdf: {exc}") from exc
    return markdown.encode("utf-8"), page_count


async def validate_upload_bytes(
    file: UploadFile, *, ext: str, settings: Settings
) -> ValidatedUpload:
    """Validate an uploaded file's size, magic bytes, and parseability; slim PDFs to Markdown.

    Streams ``file`` to a temp file in chunks (RAM-bounded), enforcing the incoming-size cap as
    it goes, checks the leading bytes against ``ext``, then deep-parses the file. PDFs are
    converted to a Markdown artifact (text + tables) and only that is returned for storage;
    other types are stored as-is. A final stored-artifact cap is enforced on the bytes to store.
    The temp file is always removed.

    Args:
        file: The uploaded file (FastAPI ``UploadFile``).
        ext: The normalized, dot-prefixed extension (already allow-listed by the caller).
        settings: Application settings holding the size caps.

    Returns:
        A :class:`ValidatedUpload` with the bytes to store and the extracted metadata.

    Raises:
        UploadValidationError: 413 (too large), or 422 (magic mismatch / unparseable / no text).
    """
    max_incoming = settings.MAX_UPLOAD_SIZE_MB * _BYTES_PER_MB
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        incoming_size = 0
        head = b""
        async with await anyio.open_file(tmp_path, "wb") as buffer:
            while chunk := await file.read(_READ_CHUNK_SIZE):
                incoming_size += len(chunk)
                if incoming_size > max_incoming:
                    raise UploadValidationError(
                        413, f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit"
                    )
                if len(head) < SNIFF_LENGTH:
                    head += chunk[: SNIFF_LENGTH - len(head)]
                await buffer.write(chunk)

        if not magic_matches_extension(head, ext):
            raise UploadValidationError(422, f"File content is not a valid {ext} file")

        page_count: int | None
        sheet_names: list[str] | None
        if ext == ".pdf":
            data, page_count = await _slim_pdf(tmp_path)
            sheet_names = None
            stored_ext = ".md"
            content_type = _MARKDOWN_CONTENT_TYPE
        else:
            page_count, sheet_names = await _parse_office_metadata(tmp_path, ext)
            async with await anyio.open_file(tmp_path, "rb") as buffer:
                data = await buffer.read()
            stored_ext = ext
            content_type = canonical_content_type(ext) or _FALLBACK_CONTENT_TYPE

        size_bytes = len(data)
        if size_bytes > settings.MAX_STORED_ARTIFACT_MB * _BYTES_PER_MB:
            raise UploadValidationError(
                413, f"Stored file exceeds the {settings.MAX_STORED_ARTIFACT_MB} MB limit"
            )

        return ValidatedUpload(
            data=data,
            size_bytes=size_bytes,
            page_count=page_count,
            sheet_names=sheet_names,
            stored_ext=stored_ext,
            content_type=content_type,
        )
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
