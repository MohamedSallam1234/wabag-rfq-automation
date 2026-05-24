"""ZIP archive safety checks for OOXML uploads (decompression-bomb guard).

``.xlsx`` and ``.docx`` are ZIP containers; a small upload can expand to a huge
payload when parsed. These helpers read only the ZIP *central directory* (no entry is
ever decompressed) and reject archives whose total uncompressed size, overall
compression ratio, or entry count exceed configured caps. The only side effect is
reading the given path with the stdlib :mod:`zipfile`.
"""

import zipfile
from dataclasses import dataclass


class ZipBombError(Exception):
    """A ZIP archive exceeds the configured decompression-safety limits."""


@dataclass(frozen=True)
class ZipStats:
    """Aggregate central-directory metrics for a ZIP archive (no extraction)."""

    entry_count: int
    total_compressed: int
    total_uncompressed: int

    @property
    def ratio(self) -> float:
        """Overall uncompressed/compressed ratio (``1.0`` when nothing is compressed)."""
        if self.total_compressed <= 0:
            return 1.0 if self.total_uncompressed == 0 else float("inf")
        return self.total_uncompressed / self.total_compressed


def inspect_zip(path: str) -> ZipStats:
    """Summarise a ZIP archive from its central directory without extracting anything.

    Args:
        path: Filesystem path to the ZIP (e.g. an OOXML ``.xlsx``/``.docx``).

    Returns:
        A :class:`ZipStats` with the entry count and total compressed/uncompressed sizes.

    Raises:
        zipfile.BadZipFile: If the file is not a readable ZIP.
    """
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
    return ZipStats(
        entry_count=len(infos),
        total_compressed=sum(info.compress_size for info in infos),
        total_uncompressed=sum(info.file_size for info in infos),
    )


def assert_zip_within_limits(
    path: str,
    *,
    max_uncompressed_bytes: int,
    max_ratio: float,
    max_entries: int,
) -> None:
    """Reject a ZIP whose decompressed footprint looks like a bomb.

    Args:
        path: Filesystem path to the ZIP archive.
        max_uncompressed_bytes: Cap on the sum of entries' uncompressed sizes.
        max_ratio: Cap on the overall uncompressed/compressed ratio.
        max_entries: Cap on the number of entries.

    Raises:
        ZipBombError: If any cap is exceeded.
        zipfile.BadZipFile: If the file is not a readable ZIP.
    """
    stats = inspect_zip(path)
    if stats.entry_count > max_entries:
        raise ZipBombError(f"archive has {stats.entry_count} entries (max {max_entries})")
    if stats.total_uncompressed > max_uncompressed_bytes:
        raise ZipBombError(
            f"archive expands to {stats.total_uncompressed} bytes (max {max_uncompressed_bytes})"
        )
    if stats.ratio > max_ratio:
        raise ZipBombError(f"archive compression ratio {stats.ratio:.1f} exceeds max {max_ratio}")
