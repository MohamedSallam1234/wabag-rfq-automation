"""PDF parsing helpers using pypdf.

Opening the file also serves as the integrity check for PDFs: a corrupt or
truncated file raises, which the upload pipeline turns into a ``failed`` document.
"""

from pypdf import PdfReader


def extract_pdf_page_count(path: str) -> int:
    """Return the number of pages in a PDF.

    Args:
        path: Filesystem path to the PDF.

    Returns:
        The page count.

    Raises:
        Exception: If the file is not a readable PDF (propagated from pypdf).
    """
    reader = PdfReader(path)
    return len(reader.pages)
