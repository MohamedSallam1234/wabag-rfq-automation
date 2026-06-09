r"""Magic-byte file-type sniffing and extension/content-type helpers (pure, no deps).

Used to reject files whose contents don't match their extension without pulling in
a native ``libmagic`` dependency.

A note on Office files: ``.docx`` and ``.xlsx`` are **OOXML containers**, which on
disk are ZIP archives — both start with the same ZIP signature (``PK\x03\x04``).
Magic bytes therefore cannot, on their own, distinguish ``.docx`` from ``.xlsx``
(or from a plain renamed ``.zip``). We do **not** accept ``.zip`` uploads; this
check only confirms the broad container family. The authoritative distinction is
the deep-parse step in :mod:`app.services.ingestion.validation` (``openpyxl`` for
``.xlsx``, ``python-docx`` for ``.docx``, ``pypdf`` for ``.pdf``), which rejects a
mismatched or disguised file by failing to parse it.
"""

from pathlib import PurePosixPath

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # OOXML (.docx/.xlsx) containers begin with this
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy .xls

#: Number of leading bytes needed to identify every supported family.
SNIFF_LENGTH = 8

# Broad container family expected per extension. ".docx"/".xlsx" share the "ooxml"
# family because they are indistinguishable by magic bytes (see module docstring).
_FAMILY_BY_EXTENSION: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "ooxml",
    ".xlsx": "ooxml",
    ".xls": "ole2",
}

_CONTENT_TYPE_BY_EXTENSION: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


def normalize_extension(filename: str) -> str:
    """Return the lowercase, dot-prefixed extension of a filename (``""`` if none)."""
    return PurePosixPath(filename.replace("\\", "/")).suffix.lower()


def sniff_family(head: bytes) -> str:
    """Identify the broad container family from a file's leading bytes.

    Args:
        head: The first bytes of the file (at least :data:`SNIFF_LENGTH`).

    Returns:
        One of ``"pdf"``, ``"ooxml"`` (a ZIP container, i.e. ``.docx``/``.xlsx``),
        ``"ole2"`` (legacy ``.xls``), or ``"unknown"``.
    """
    if head.startswith(_PDF_MAGIC):
        return "pdf"
    if head.startswith(_ZIP_MAGIC):
        return "ooxml"
    if head.startswith(_OLE2_MAGIC):
        return "ole2"
    return "unknown"


def expected_family(ext: str) -> str | None:
    """Return the magic-byte family expected for an extension, or ``None`` if unknown."""
    return _FAMILY_BY_EXTENSION.get(ext.lower())


def magic_matches_extension(head: bytes, ext: str) -> bool:
    """Report whether the file's magic bytes are consistent with its extension.

    This is a coarse gate only; ``.docx`` vs ``.xlsx`` is resolved by the
    deep-parse step, not here (see module docstring).
    """
    family = expected_family(ext)
    return family is not None and sniff_family(head) == family


def canonical_content_type(ext: str) -> str | None:
    """Return the canonical MIME type for a supported extension, or ``None``."""
    return _CONTENT_TYPE_BY_EXTENSION.get(ext.lower())
