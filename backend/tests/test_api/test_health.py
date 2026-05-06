"""Test the health endpoint."""

from fastapi.testclient import TestClient

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
