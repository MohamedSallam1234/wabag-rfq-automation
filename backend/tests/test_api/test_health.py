"""Test the health and readiness endpoints."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import main
from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_health() -> None:
    """Test that the health endpoint returns 200 and the correct payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "env": settings.APP_ENV,
    }


def test_ready_returns_200_when_db_ok() -> None:
    """Readiness is 200 when the DB ping succeeds."""
    with patch.object(main, "ping_db", AsyncMock()):
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_db_unreachable() -> None:
    """Readiness is 503 when the DB ping fails."""
    with patch.object(main, "ping_db", AsyncMock(side_effect=RuntimeError("db down"))):
        response = client.get("/ready")
    assert response.status_code == 503
