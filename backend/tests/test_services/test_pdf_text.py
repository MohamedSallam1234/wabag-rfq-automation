"""Tests for born-digital PDF → Markdown extraction (text + tables, no-text guard)."""

import io
import os
import tempfile
from collections.abc import Iterator

import pytest
from pypdf import PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

from app.services.ingestion.pdf_text import NoExtractableTextError, extract_pdf_markdown


# --------------------------------------------------------------------------- #
# PDF-fixture builders
# --------------------------------------------------------------------------- #
def _text_table_pdf_bytes(pages: int = 1) -> bytes:
    """A born-digital PDF with a paragraph and a bordered table on each page."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story: list[object] = []
    for i in range(pages):
        story.append(Paragraph("Equipment specification for centrifugal pumps.", styles["Normal"]))
        rows = [
            ["Tag", "Description", "Qty"],
            ["P-101", "Centrifugal pump", "2"],
            ["V-201", "Pressure vessel", "1"],
        ]
        table = Table(rows)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
        story.append(table)
        if i < pages - 1:
            story.append(PageBreak())
    doc.build(story)
    return buffer.getvalue()


def _blank_pdf_bytes(pages: int = 1) -> bytes:
    """An image-free, textless PDF — stands in for a scanned / image-only document."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _write_temp_pdf(data: bytes) -> Iterator[str]:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    with open(path, "wb") as handle:
        handle.write(data)
    try:
        yield path
    finally:
        os.unlink(path)


@pytest.fixture
def text_table_pdf() -> Iterator[str]:
    yield from _write_temp_pdf(_text_table_pdf_bytes(pages=1))


@pytest.fixture
def two_page_pdf() -> Iterator[str]:
    yield from _write_temp_pdf(_text_table_pdf_bytes(pages=2))


@pytest.fixture
def blank_pdf() -> Iterator[str]:
    yield from _write_temp_pdf(_blank_pdf_bytes(pages=1))


@pytest.fixture
def blank_pdf_multipage() -> Iterator[str]:
    yield from _write_temp_pdf(_blank_pdf_bytes(pages=5))


# --------------------------------------------------------------------------- #
# extract_pdf_markdown
# --------------------------------------------------------------------------- #
def test_extracts_text_and_table_as_markdown(text_table_pdf: str) -> None:
    markdown, page_count = extract_pdf_markdown(text_table_pdf)

    assert page_count == 1
    # Paragraph text survives.
    assert "centrifugal pumps" in markdown.lower()
    # Table is preserved as a GitHub-flavored Markdown table (header separator + cell values).
    assert "---" in markdown
    assert markdown.count("|") >= 6
    assert "P-101" in markdown
    assert "Pressure vessel" in markdown


def test_reports_page_count(two_page_pdf: str) -> None:
    _, page_count = extract_pdf_markdown(two_page_pdf)
    assert page_count == 2


def test_textless_pdf_raises_no_extractable_text(blank_pdf: str) -> None:
    with pytest.raises(NoExtractableTextError):
        extract_pdf_markdown(blank_pdf)


def test_textless_multipage_pdf_raises_no_extractable_text(blank_pdf_multipage: str) -> None:
    # The fast pre-check must scan every page before concluding there is no text layer (and
    # bail out before the expensive table detector runs).
    with pytest.raises(NoExtractableTextError):
        extract_pdf_markdown(blank_pdf_multipage)
