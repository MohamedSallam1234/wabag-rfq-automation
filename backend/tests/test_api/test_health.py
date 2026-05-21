"""Test the health and readiness endpoints."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api.deps import get_storage
from app.core.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def test_health() -> None:
    """Test that the health endpoint returns 200 and the correct payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "env": settings.APP_ENV,
    }


def test_ready_returns_200_when_db_and_storage_ok() -> None:
    """Readiness is 200 when the DB ping succeeds and the storage client is wired."""
    storage = MagicMock()
    app.dependency_overrides[get_storage] = lambda: storage
    with patch.object(main, "ping_db", AsyncMock()):
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_db_unreachable() -> None:
    """Readiness is 503 when the DB ping fails."""
    storage = MagicMock()
    app.dependency_overrides[get_storage] = lambda: storage
    with patch.object(main, "ping_db", AsyncMock(side_effect=RuntimeError("db down"))):
        response = client.get("/ready")
    assert response.status_code == 503


def test_ready_returns_503_when_storage_missing() -> None:
    """Readiness is 503 when the storage client is not wired."""
    app.dependency_overrides[get_storage] = lambda: None
    with patch.object(main, "ping_db", AsyncMock()):
        response = client.get("/ready")
    assert response.status_code == 503
