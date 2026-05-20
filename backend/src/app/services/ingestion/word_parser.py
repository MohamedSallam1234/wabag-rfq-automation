"""Word document parsing helpers using python-docx.

Opening the document is the integrity check for ``.docx`` files and distinguishes a
real Word document from an ``.xlsx`` or plain ZIP sharing the OOXML magic bytes.
"""

from docx import Document


def validate_docx(path: str) -> None:
    """Validate that a file is a readable ``.docx`` document.

    Args:
        path: Filesystem path to the document.

    Raises:
        Exception: If the file is not a readable ``.docx`` document.
    """
    Document(path)
