"""Synchronous upload validation: size guard, magic-byte check, and deep parse.

The client POSTs the file bytes to the backend, which streams them to a temp file on
disk (RAM-bounded), checks the magic bytes against the extension, and deep-parses the
file to reject corrupt or mismatched content. Only files that pass are uploaded to
storage — an invalid file is a synchronous 4xx and nothing is ever stored.
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
from app.services.ingestion.filetype import SNIFF_LENGTH, magic_matches_extension
from app.services.ingestion.pdf_parser import extract_pdf_page_count
from app.services.ingestion.word_parser import validate_docx

_BYTES_PER_MB = 1024 * 1024
_READ_CHUNK_SIZE = 1024 * 1024


class UploadValidationError(Exception):
    """An upload failed validation; carries the HTTP status to surface to the client."""

    def __init__(self, status_code: int, detail: str) -> None:
        """Store the HTTP ``status_code`` and human-readable ``detail``."""
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class ValidatedUpload:
    """The validated bytes of an upload plus the metadata extracted while parsing."""

    data: bytes
    size_bytes: int
    page_count: int | None
    sheet_names: list[str] | None


def plan_storage_path(project_id: uuid.UUID, document_id: uuid.UUID, ext: str) -> str:
    """Build the storage object key for a document: ``{project_id}/{document_id}{ext}``."""
    return f"{project_id}/{document_id}{ext}"


async def _deep_parse(tmp_path: str, ext: str) -> tuple[int | None, list[str] | None]:
    """Parse the file off the event loop; return ``(page_count, sheet_names)``.

    Opening the file with the format's parser is the integrity check: a corrupt file, or
    one whose real type does not match its extension (e.g. an ``.xlsx`` renamed ``.docx``),
    fails to parse. ``.xls`` has no parser and is accepted as a stored blob.

    Raises:
        UploadValidationError: 422 if the file cannot be parsed as its declared type.
    """
    try:
        if ext == ".pdf":
            return await anyio.to_thread.run_sync(extract_pdf_page_count, tmp_path), None
        if ext == ".xlsx":
            return None, await anyio.to_thread.run_sync(extract_xlsx_sheet_names, tmp_path)
        if ext == ".docx":
            await anyio.to_thread.run_sync(validate_docx, tmp_path)
            return None, None
    except Exception as exc:
        raise UploadValidationError(422, f"File could not be parsed as {ext}: {exc}") from exc
    return None, None  # .xls: accepted as a stored blob (no parser available)


async def validate_upload_bytes(
    file: UploadFile, *, ext: str, settings: Settings
) -> ValidatedUpload:
    """Validate an uploaded file's size, magic bytes, and parseability.

    Streams ``file`` to a temp file in chunks (RAM-bounded), enforcing the size cap as it
    goes, checks the leading bytes against ``ext``, then deep-parses the file. The temp
    file is always removed. The validated bytes are returned for the caller to store.

    Args:
        file: The uploaded file (FastAPI ``UploadFile``).
        ext: The normalized, dot-prefixed extension (already allow-listed by the caller).
        settings: Application settings holding the size cap.

    Returns:
        A :class:`ValidatedUpload` with the bytes and the extracted metadata.

    Raises:
        UploadValidationError: 413 (too large), or 422 (magic mismatch / unparseable).
    """
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * _BYTES_PER_MB
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        size = 0
        head = b""
        async with await anyio.open_file(tmp_path, "wb") as buffer:
            while chunk := await file.read(_READ_CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise UploadValidationError(
                        413, f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit"
                    )
                if len(head) < SNIFF_LENGTH:
                    head += chunk[: SNIFF_LENGTH - len(head)]
                await buffer.write(chunk)

        if not magic_matches_extension(head, ext):
            raise UploadValidationError(422, f"File content is not a valid {ext} file")

        page_count, sheet_names = await _deep_parse(tmp_path, ext)

        async with await anyio.open_file(tmp_path, "rb") as buffer:
            data = await buffer.read()
        return ValidatedUpload(
            data=data, size_bytes=size, page_count=page_count, sheet_names=sheet_names
        )
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
