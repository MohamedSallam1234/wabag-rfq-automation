"""Tests for the opt-in ClamAV scanner wrapper."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.config import get_settings
from app.services.ingestion import antivirus
from app.services.ingestion.antivirus import ScanResult, scan_file

SETTINGS = get_settings()


def _enabled() -> object:
    """Settings copy with AV scanning turned on."""
    return SETTINGS.model_copy(update={"AV_SCAN_ENABLED": True})


async def test_scan_file_noop_when_disabled() -> None:
    # AV_SCAN_ENABLED defaults to False → always clean, never touches the filesystem.
    result = await scan_file("/does/not/exist", SETTINGS)
    assert result == ScanResult(clean=True)


async def test_scan_file_clean(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"harmless")
    client = MagicMock()
    client.instream.return_value = {"stream": ("OK", None)}
    with patch.object(antivirus, "_build_client", return_value=client):
        result = await scan_file(str(path), _enabled())
    assert result == ScanResult(clean=True)


async def test_scan_file_infected(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"x")
    client = MagicMock()
    client.instream.return_value = {"stream": ("FOUND", "Eicar-Test-Signature")}
    with patch.object(antivirus, "_build_client", return_value=client):
        result = await scan_file(str(path), _enabled())
    assert result.clean is False
    assert result.signature == "Eicar-Test-Signature"
    assert result.error is None


async def test_scan_file_error_when_scanner_unreachable(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"x")
    with patch.object(antivirus, "_build_client", side_effect=ConnectionError("refused")):
        result = await scan_file(str(path), _enabled())
    assert result.clean is False
    assert result.signature is None  # could-not-verify, not infected
    assert result.error is not None
