"""Born-digital PDF → Markdown extraction (text + tables) via pymupdf4llm.

Employer technical specifications can run to hundreds or thousands of pages and are bloated
by images, embedded fonts, and color. For RFQ automation the model only needs the text and
tables, so at upload time we convert born-digital PDFs to a compact Markdown artifact and
store only that. Scanned / image-only PDFs have no extractable text and are rejected upstream
(no OCR).

``pymupdf4llm`` (and its PyMuPDF backend) are AGPL-3.0 — acceptable for this internal-only tool.
"""

import pymupdf
import pymupdf4llm

#: Minimum alphanumeric characters a PDF must yield from a plain text-layer scan to be treated
#: as born-digital. Below this we reject it as image-only (scanned, "Print to PDF", or
#: text-as-outlines) — there is no extractable text to slim, and no OCR.
_MIN_TEXT_CHARS = 16


class NoExtractableTextError(Exception):
    """Raised when a PDF yields no extractable text (image-only / scanned; no OCR)."""


def _has_text_layer(doc: pymupdf.Document) -> bool:
    """Cheaply report whether the PDF has an extractable text layer.

    Uses PyMuPDF's plain ``get_text`` (no table detection), accumulating alphanumeric characters
    and stopping as soon as the threshold is reached. This is the **fast pre-check**: a
    born-digital doc trips the threshold on its first page or two, while an image-only doc is
    scanned in full (seconds) and rejected — *before* the expensive ``pymupdf4llm`` table
    detector, which would otherwise grind for many minutes over a graphics-heavy, textless PDF.
    """
    alnum = 0
    for i in range(doc.page_count):
        page = doc.load_page(i)
        alnum += sum(ch.isalnum() for ch in page.get_text("text"))
        if alnum >= _MIN_TEXT_CHARS:
            return True
    return False


def extract_pdf_markdown(path: str) -> tuple[str, int]:
    """Convert a born-digital PDF to Markdown (text + tables); return ``(markdown, page_count)``.

    Args:
        path: Filesystem path to the PDF.

    Returns:
        The extracted GitHub-flavored Markdown (tables preserved) and the PDF's page count.

    Raises:
        NoExtractableTextError: The PDF has no extractable text layer (image-only / scanned).
        Exception: If the file is not a readable PDF (propagated from PyMuPDF); this includes
            encrypted / password-protected files.
    """
    doc = pymupdf.open(path)
    try:
        page_count: int = doc.page_count
        if not _has_text_layer(doc):
            raise NoExtractableTextError("no extractable text layer")
        markdown: str = pymupdf4llm.to_markdown(doc, show_progress=False)
    finally:
        doc.close()
    return markdown, page_count
