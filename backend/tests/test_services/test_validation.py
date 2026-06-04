"""Tests for synchronous upload validation (size guard, magic bytes, deep parse)."""

import io
import uuid

import pytest
from docx import Document as DocxDocument
from openpyxl import Workbook
from pypdf import PdfWriter

from app.core.config import get_settings
from app.services.ingestion import validation
from app.services.ingestion.validation import UploadValidationError, validate_upload_bytes

SETTINGS = get_settings()


# --------------------------------------------------------------------------- #
# File-fixture builders (valid, parseable office files)
# --------------------------------------------------------------------------- #
def _pdf_bytes(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _docx_bytes() -> bytes:
    document = DocxDocument()
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


_OLE2_BYTES = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32


class _FakeUpload:
    """Minimal async file stand-in exposing the ``read`` coroutine the validator uses."""

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


# --------------------------------------------------------------------------- #
# Pure helper
# --------------------------------------------------------------------------- #
def test_plan_storage_path() -> None:
    project_id = uuid.uuid4()
    document_id = uuid.uuid4()
    assert validation.plan_storage_path(project_id, document_id, ".pdf") == (
        f"{project_id}/{document_id}.pdf"
    )


# --------------------------------------------------------------------------- #
# validate_upload_bytes
# --------------------------------------------------------------------------- #
async def test_validate_pdf_returns_page_count() -> None:
    result = await validate_upload_bytes(
        _FakeUpload(_pdf_bytes(pages=2)), ext=".pdf", settings=SETTINGS
    )
    assert result.page_count == 2
    assert result.sheet_names is None
    assert result.data.startswith(b"%PDF-")
    assert result.size_bytes == len(result.data)


async def test_validate_xlsx_returns_sheet_names() -> None:
    result = await validate_upload_bytes(_FakeUpload(_xlsx_bytes()), ext=".xlsx", settings=SETTINGS)
    assert result.sheet_names == ["Sheet"]
    assert result.page_count is None


async def test_validate_docx_ok() -> None:
    result = await validate_upload_bytes(_FakeUpload(_docx_bytes()), ext=".docx", settings=SETTINGS)
    assert result.page_count is None
    assert result.sheet_names is None


async def test_validate_xls_accepted_as_blob() -> None:
    result = await validate_upload_bytes(_FakeUpload(_OLE2_BYTES), ext=".xls", settings=SETTINGS)
    assert result.page_count is None
    assert result.sheet_names is None
    assert result.size_bytes == len(_OLE2_BYTES)


async def test_validate_magic_mismatch_raises_422() -> None:
    with pytest.raises(UploadValidationError) as exc:
        await validate_upload_bytes(
            _FakeUpload(b"definitely not a pdf"), ext=".pdf", settings=SETTINGS
        )
    assert exc.value.status_code == 422


async def test_validate_unparseable_ooxml_raises_422() -> None:
    # Has the ZIP magic so it clears the coarse gate, but is not a real .xlsx.
    with pytest.raises(UploadValidationError) as exc:
        await validate_upload_bytes(
            _FakeUpload(b"PK\x03\x04 not really a zip"), ext=".xlsx", settings=SETTINGS
        )
    assert exc.value.status_code == 422


async def test_validate_oversized_raises_413(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0)
    with pytest.raises(UploadValidationError) as exc:
        await validate_upload_bytes(_FakeUpload(_pdf_bytes(pages=1)), ext=".pdf", settings=settings)
    assert exc.value.status_code == 413


async def test_validate_huge_file_raises_413_mid_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """A payload that exceeds the cap part-way through streaming is rejected (413)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)  # 1 MB cap
    payload = b"x" * (2 * 1024 * 1024)  # 2 MB → trips on the second chunk
    with pytest.raises(UploadValidationError) as exc:
        await validate_upload_bytes(_FakeUpload(payload), ext=".pdf", settings=settings)
    assert exc.value.status_code == 413
