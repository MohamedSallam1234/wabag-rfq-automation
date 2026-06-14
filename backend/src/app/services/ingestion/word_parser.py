"""Word (.docx) → Markdown extraction (headings, paragraphs, tables) via python-docx.

Opening the document is also the integrity check for ``.docx`` files and distinguishes a
real Word document from an ``.xlsx`` or plain ZIP sharing the OOXML magic bytes: those fail
to open. The body is walked in document order so headings, paragraphs, and tables keep their
original sequence; images and other non-text content are dropped.
"""

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.ingestion.markdown_table import gfm_table

_MAX_HEADING_LEVEL = 6


def _heading_level(style_name: str) -> int:
    """Return the Markdown heading level for a paragraph style name (0 = not a heading).

    Maps Word's ``Title`` and ``Heading 1``..``Heading 9`` styles to ``#``..``######``
    (clamped at level 6, the deepest Markdown heading).
    """
    if style_name == "Title":
        return 1
    if style_name.startswith("Heading "):
        try:
            level = int(style_name.removeprefix("Heading "))
        except ValueError:
            return 0
        return min(level, _MAX_HEADING_LEVEL)
    return 0


def _paragraph_markdown(paragraph: Paragraph) -> str:
    """Render a paragraph as Markdown (heading or plain text); ``""`` if it is empty."""
    text = paragraph.text.strip()
    if not text:
        return ""
    style_name = paragraph.style.name if paragraph.style is not None else None
    level = _heading_level(style_name or "")
    return f"{'#' * level} {text}" if level else text


def _table_markdown(table: Table) -> str:
    """Render a Word table as a GFM table; ``""`` if it has no rows."""
    rows = [[cell.text for cell in row.cells] for row in table.rows]
    return gfm_table(rows) if rows else ""


def extract_docx_markdown(path: str) -> str:
    """Convert a ``.docx`` document to Markdown (headings + paragraphs + tables).

    Args:
        path: Filesystem path to the document.

    Returns:
        The extracted Markdown. An empty (text-free) document yields ``""``.

    Raises:
        Exception: If the file is not a readable ``.docx`` document (propagated from
            python-docx); the caller maps this to a 422.
    """
    document = Document(path)
    blocks: list[str] = []
    for item in document.iter_inner_content():
        rendered = (
            _paragraph_markdown(item) if isinstance(item, Paragraph) else _table_markdown(item)
        )
        if rendered:
            blocks.append(rendered)
    return "\n\n".join(blocks)
