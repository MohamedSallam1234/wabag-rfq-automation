"""Synchronous upload validation: size guard, magic-byte check, deep parse, and Markdown slimming.

The client POSTs the file bytes to the backend, which streams them to a temp file on disk
(RAM-bounded), checks the magic bytes against the extension, and deep-parses the file to reject
corrupt or mismatched content. Every supported type (``.pdf``/``.docx``/``.xlsx``/``.xls``) is
converted to a compact Markdown artifact (text + tables) and only that slim version is stored —
the heavy original is discarded. Only files that pass are uploaded to storage; an invalid file
is a synchronous 4xx and nothing is ever stored.

Two size caps apply: the *incoming body* cap (``MAX_UPLOAD_SIZE_MB``) can be large because the
original is discarded, while the *stored artifact* cap (``MAX_STORED_ARTIFACT_MB``) matches the
Supabase bucket ``file_size_limit`` and is checked against the final stored Markdown bytes.
"""

import contextlib
import logging
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath

import anyio
from fastapi import UploadFile

from app.core.config import Settings
from app.services.ingestion.excel_parser import extract_xls_markdown, extract_xlsx_markdown
from app.services.ingestion.filetype import SNIFF_LENGTH, magic_matches_extension
from app.services.ingestion.pdf_text import NoExtractableTextError, extract_pdf_markdown
from app.services.ingestion.word_parser import extract_docx_markdown

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024
_READ_CHUNK_SIZE = 1024 * 1024
_MARKDOWN_CONTENT_TYPE = "text/markdown"
#: Characters not allowed in a storage object name; collapsed to "_" when building the key.
_UNSAFE_OBJECT_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f/\\]+")


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

    ``data``/``size_bytes`` describe the *stored* artifact, which is always the extracted
    Markdown (``stored_ext=".md"``, ``content_type="text/markdown"``) regardless of the source
    type. ``page_count`` is set only for PDFs and ``sheet_names`` only for spreadsheets.
    """

    data: bytes
    size_bytes: int
    page_count: int | None
    sheet_names: list[str] | None
    stored_ext: str
    content_type: str


def _safe_object_name(filename: str, fallback: str) -> str:
    """Sanitize a filename into a single safe storage object-name component.

    Takes the basename (dropping any directory parts a client may have sent), strips control
    characters and path separators, and falls back to ``fallback`` if nothing usable remains.
    The raw filename is still persisted in the DB ``original_filename`` column; only the storage
    key is sanitized.
    """
    base = PurePosixPath(filename.replace("\\", "/")).name
    safe = _UNSAFE_OBJECT_NAME_CHARS.sub("_", base).strip("_. ")
    return safe or fallback


def plan_storage_path(
    project_id: uuid.UUID, document_id: uuid.UUID, filename: str, stored_ext: str
) -> str:
    """Build the storage object key for a document.

    Layout: ``projects/{project_id}/documents/{document_id}/{safe_filename}{stored_ext}`` — each
    document gets its own folder and the object keeps the human-readable original name (including
    its source extension) with the stored ``.md`` suffix appended.
    """
    safe_name = _safe_object_name(filename, str(document_id))
    return f"projects/{project_id}/documents/{document_id}/{safe_name}{stored_ext}"


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
        logger.exception("PDF parse failed")
        raise UploadValidationError(422, "File could not be parsed as .pdf") from exc
    return markdown.encode("utf-8"), page_count


async def _slim_docx(tmp_path: str) -> bytes:
    """Convert a ``.docx`` to Markdown bytes off the event loop.

    Raises:
        UploadValidationError: 422 if the file cannot be parsed as a ``.docx``.
    """
    try:
        markdown = await anyio.to_thread.run_sync(extract_docx_markdown, tmp_path)
    except Exception as exc:
        logger.exception("DOCX parse failed")
        raise UploadValidationError(422, "File could not be parsed as .docx") from exc
    return markdown.encode("utf-8")


async def _slim_xlsx(tmp_path: str) -> tuple[bytes, list[str]]:
    """Convert an ``.xlsx`` to Markdown bytes off the event loop; return ``(data, sheet_names)``.

    Raises:
        UploadValidationError: 422 if the file cannot be parsed as an ``.xlsx``.
    """
    try:
        markdown, sheet_names = await anyio.to_thread.run_sync(extract_xlsx_markdown, tmp_path)
    except Exception as exc:
        logger.exception("XLSX parse failed")
        raise UploadValidationError(422, "File could not be parsed as .xlsx") from exc
    return markdown.encode("utf-8"), sheet_names


async def _slim_xls(tmp_path: str) -> tuple[bytes, list[str]]:
    """Convert a legacy ``.xls`` to Markdown bytes off the event loop; return ``(data, names)``.

    Raises:
        UploadValidationError: 422 if the file cannot be parsed as an ``.xls`` workbook.
    """
    try:
        markdown, sheet_names = await anyio.to_thread.run_sync(extract_xls_markdown, tmp_path)
    except Exception as exc:
        logger.exception("XLS parse failed")
        raise UploadValidationError(422, "File could not be parsed as .xls") from exc
    return markdown.encode("utf-8"), sheet_names


async def validate_upload_bytes(
    file: UploadFile, *, ext: str, settings: Settings
) -> ValidatedUpload:
    """Validate an uploaded file's size, magic bytes, and parseability; slim it to Markdown.

    Streams ``file`` to a temp file in chunks (RAM-bounded), enforcing the incoming-size cap as
    it goes, checks the leading bytes against ``ext``, then deep-parses the file. Every supported
    type is converted to a Markdown artifact (text + tables) and only that is returned for
    storage. A final stored-artifact cap is enforced on the bytes to store. The temp file is
    always removed.

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

        # Every supported type is slimmed to a Markdown artifact (stored as ``.md``). Only the
        # extracted metadata differs: page_count for PDFs, sheet_names for spreadsheets.
        page_count: int | None = None
        sheet_names: list[str] | None = None
        if ext == ".pdf":
            data, page_count = await _slim_pdf(tmp_path)
        elif ext == ".docx":
            data = await _slim_docx(tmp_path)
        elif ext == ".xlsx":
            data, sheet_names = await _slim_xlsx(tmp_path)
        else:  # ".xls"
            data, sheet_names = await _slim_xls(tmp_path)
        stored_ext = ".md"
        content_type = _MARKDOWN_CONTENT_TYPE

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
