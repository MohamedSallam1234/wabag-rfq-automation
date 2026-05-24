"""Opt-in malware scanning of uploaded files via ClamAV (clamd).

Scanning is disabled by default (``AV_SCAN_ENABLED``); when enabled, the downloaded
bytes are scanned during background validation, off the event loop. A scanner failure
is reported distinctly from an infection so the caller can *fail closed* (retry rather
than accept an unscanned file). Use ``CLAMD_SOCKET`` for a local unix socket, or
``CLAMD_HOST``/``CLAMD_PORT`` for a network clamd.
"""

import logging
from dataclasses import dataclass
from typing import Any

import anyio
import clamd

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    """Outcome of an antivirus scan.

    ``clean=True`` when scanning is disabled or the file is verified clean.
    ``signature`` names the detected threat when the file is infected. ``error`` is
    set when the scanner itself failed — callers must treat that as "could not verify",
    not "clean" and not "infected".
    """

    clean: bool
    signature: str | None = None
    error: str | None = None


def _build_client(settings: Settings) -> Any:
    """Build a clamd client from settings (unix socket preferred, else network)."""
    if settings.CLAMD_SOCKET:
        return clamd.ClamdUnixSocket(path=settings.CLAMD_SOCKET, timeout=settings.CLAMD_TIMEOUT_S)
    return clamd.ClamdNetworkSocket(
        host=settings.CLAMD_HOST or "localhost",
        port=settings.CLAMD_PORT,
        timeout=settings.CLAMD_TIMEOUT_S,
    )


def _scan_sync(path: str, settings: Settings) -> ScanResult:
    """Stream a file to clamd and map its verdict to a :class:`ScanResult` (blocking)."""
    client = _build_client(settings)
    with open(path, "rb") as stream:
        response = client.instream(stream)
    # clamd returns e.g. {"stream": ("OK", None)} or {"stream": ("FOUND", "Eicar-Test")}.
    status, signature = response["stream"]
    if status == "OK":
        return ScanResult(clean=True)
    return ScanResult(clean=False, signature=signature or status)


async def scan_file(path: str, settings: Settings) -> ScanResult:
    """Scan a file for malware when scanning is enabled, else return a clean result.

    Args:
        path: Filesystem path to the file to scan.
        settings: Application settings (scanner toggle + connection details).

    Returns:
        A :class:`ScanResult`. With ``AV_SCAN_ENABLED`` false, always clean. A
        scanner/connection failure yields ``clean=False`` with ``error`` set and no
        ``signature`` — that means "could not verify", which the caller should retry.
    """
    if not settings.AV_SCAN_ENABLED:
        return ScanResult(clean=True)
    try:
        return await anyio.to_thread.run_sync(_scan_sync, path, settings)
    except Exception as exc:  # connection refused / timeout / protocol error
        logger.warning("antivirus scan failed for %s: %s", path, exc)
        return ScanResult(clean=False, error=str(exc))
