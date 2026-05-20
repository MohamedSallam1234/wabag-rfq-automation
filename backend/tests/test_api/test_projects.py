"""Tests for the project endpoints (owner-scoped)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.project import Project


async def _fake_refresh(instance: object, *_: object, **__: object) -> None:
    now = datetime.now(UTC)
    if getattr(instance, "id", None) is None:
        instance.id = uuid.uuid4()  # type: ignore[attr-defined]
    if getattr(instance, "created_at", None) is None:
        instance.created_at = now  # type: ignore[attr-defined]
    if getattr(instance, "updated_at", None) is None:
        instance.updated_at = now  # type: ignore[attr-defined]


def _make_session() -> MagicMock:
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=_fake_refresh)
    session.get = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_project(owner_id: uuid.UUID) -> Project:
    now = datetime.now(UTC)
    return Project(
        id=uuid.uuid4(), owner_id=owner_id, name="Kohafa WWTP", created_at=now, updated_at=now
    )


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def test_create_project() -> None:
    owner = uuid.uuid4()
    session = _make_session()
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session

    client = TestClient(app)
    response = client.post("/api/v1/projects", json={"name": "Kohafa WWTP"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Kohafa WWTP"
    assert body["owner_id"] == str(owner)
    session.add.assert_called_once()


def test_list_projects_only_returns_callers() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    session = _make_session()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [project]
    session.execute = AsyncMock(return_value=result)
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session

    client = TestClient(app)
    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_project_owned() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    session = _make_session()
    session.get = AsyncMock(return_value=project)
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session

    client = TestClient(app)
    response = client.get(f"/api/v1/projects/{project.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(project.id)


def test_get_project_not_owned_returns_404() -> None:
    project = _make_project(uuid.uuid4())
    session = _make_session()
    session.get = AsyncMock(return_value=project)
    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid.uuid4())}
    app.dependency_overrides[get_db] = lambda: session

    client = TestClient(app)
    response = client.get(f"/api/v1/projects/{project.id}")

    assert response.status_code == 404
