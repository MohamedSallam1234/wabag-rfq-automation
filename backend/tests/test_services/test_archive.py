"""Tests for the OOXML zip-bomb guard."""

import zipfile
from pathlib import Path

import pytest

from app.services.ingestion.archive import (
    ZipBombError,
    assert_zip_within_limits,
    inspect_zip,
)


def _make_zip(path: str, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)


def test_inspect_zip_reports_totals(tmp_path: Path) -> None:
    path = str(tmp_path / "a.zip")
    payload = b"hello world" * 100
    _make_zip(path, [("a.txt", payload)])
    stats = inspect_zip(path)
    assert stats.entry_count == 1
    assert stats.total_uncompressed == len(payload)
    assert stats.total_compressed > 0
    assert stats.ratio > 1


def test_assert_within_limits_passes_for_normal_zip(tmp_path: Path) -> None:
    path = str(tmp_path / "ok.zip")
    _make_zip(path, [("a.txt", b"some modest content")])
    # Should not raise.
    assert_zip_within_limits(path, max_uncompressed_bytes=10_000, max_ratio=100, max_entries=100)


def test_assert_rejects_oversized_uncompressed(tmp_path: Path) -> None:
    path = str(tmp_path / "big.zip")
    _make_zip(path, [("a.txt", b"x" * 10_000)])
    with pytest.raises(ZipBombError, match="expands"):
        assert_zip_within_limits(
            path, max_uncompressed_bytes=100, max_ratio=10_000, max_entries=100
        )


def test_assert_rejects_high_ratio(tmp_path: Path) -> None:
    path = str(tmp_path / "bomb.zip")
    # Highly compressible payload → very high uncompressed/compressed ratio.
    _make_zip(path, [("a.txt", b"\x00" * 1_000_000)])
    with pytest.raises(ZipBombError, match="ratio"):
        assert_zip_within_limits(
            path, max_uncompressed_bytes=10_000_000, max_ratio=5, max_entries=100
        )


def test_assert_rejects_too_many_entries(tmp_path: Path) -> None:
    path = str(tmp_path / "many.zip")
    _make_zip(path, [(f"f{i}.txt", b"a") for i in range(10)])
    with pytest.raises(ZipBombError, match="entries"):
        assert_zip_within_limits(
            path, max_uncompressed_bytes=10_000_000, max_ratio=10_000, max_entries=5
        )
