"""Tests for magic-byte file-type sniffing and extension helpers."""

import pytest

from app.services.ingestion import filetype

_PDF = b"%PDF-1.7\n..."
_OOXML = b"PK\x03\x04rest"
_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1more"
_GARBAGE = b"this is plain text"


@pytest.mark.parametrize(
    ("head", "family"),
    [
        (_PDF, "pdf"),
        (_OOXML, "ooxml"),
        (_OLE2, "ole2"),
        (_GARBAGE, "unknown"),
        (b"", "unknown"),
    ],
)
def test_sniff_family(head: bytes, family: str) -> None:
    assert filetype.sniff_family(head) == family


@pytest.mark.parametrize(
    ("ext", "family"),
    [(".pdf", "pdf"), (".docx", "ooxml"), (".xlsx", "ooxml"), (".xls", "ole2"), (".txt", None)],
)
def test_expected_family(ext: str, family: str | None) -> None:
    assert filetype.expected_family(ext) == family


@pytest.mark.parametrize(
    ("head", "ext", "ok"),
    [
        (_PDF, ".pdf", True),
        (_OOXML, ".xlsx", True),
        (_OOXML, ".docx", True),  # docx/xlsx share magic; extension disambiguates
        (_OLE2, ".xls", True),
        (_GARBAGE, ".pdf", False),
        (_PDF, ".xlsx", False),
        (_PDF, ".txt", False),
    ],
)
def test_magic_matches_extension(head: bytes, ext: str, ok: bool) -> None:
    assert filetype.magic_matches_extension(head, ext) is ok


@pytest.mark.parametrize(
    ("filename", "ext"),
    [
        ("report.PDF", ".pdf"),
        ("a/b\\c.xlsx", ".xlsx"),
        ("noext", ""),
        ("archive.tar.gz", ".gz"),
    ],
)
def test_normalize_extension(filename: str, ext: str) -> None:
    assert filetype.normalize_extension(filename) == ext


def test_canonical_content_type() -> None:
    assert filetype.canonical_content_type(".pdf") == "application/pdf"
    assert filetype.canonical_content_type(".xlsx") == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert filetype.canonical_content_type(".txt") is None
