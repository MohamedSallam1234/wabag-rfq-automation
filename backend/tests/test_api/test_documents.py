"""Tests for the document endpoints (signed-upload init/finalize, owner-scoped)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from storage3.utils import StorageException

from app.api.deps import get_db, get_storage
from app.api.v1 import documents as documents_module
from app.core.security import get_current_user
from app.main import app
from app.models.document import DocTypeSource, Document, DocumentStatus, RetentionPolicy
from app.models.project import Project

_MB = 1024 * 1024


async def _fake_refresh(instance: object, *_: object, **__: object) -> None:
    now = datetime.now(UTC)
    for attr in ("created_at", "updated_at"):
        if getattr(instance, attr, None) is None:
            setattr(instance, attr, now)


def _make_session() -> MagicMock:
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock(side_effect=_fake_refresh)
    session.get = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_storage() -> tuple[MagicMock, MagicMock]:
    storage = MagicMock()
    proxy = MagicMock()
    proxy.create_signed_upload_url = AsyncMock(
        return_value={"signed_url": "https://up", "token": "tok", "path": "p"}
    )
    proxy.create_signed_url = AsyncMock(return_value={"signedURL": "https://download"})
    proxy.info = AsyncMock(return_value={"size": 1000})
    proxy.remove = AsyncMock(return_value=[])
    storage.from_ = MagicMock(return_value=proxy)
    return storage, proxy


def _usage(count: int, total: int) -> MagicMock:
    result = MagicMock()
    result.one.return_value = (count, total)
    return result


def _make_project(owner_id: uuid.UUID) -> Project:
    now = datetime.now(UTC)
    return Project(id=uuid.uuid4(), owner_id=owner_id, name="P", created_at=now, updated_at=now)


def _make_document(project_id: uuid.UUID, **overrides: object) -> Document:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "project_id": project_id,
        "original_filename": "01_Spec_Rev01.pdf",
        "storage_bucket": "rfq-documents",
        "storage_path": "proj/doc.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1000,
        "status": DocumentStatus.PENDING,
        "doc_type_source": DocTypeSource.AUTO,
        "retention": RetentionPolicy.PERSISTENT,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return Document(**defaults)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def test_init_upload_creates_pending_and_signs(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    session = _make_session()
    session.get = AsyncMock(return_value=project)
    session.execute = AsyncMock(return_value=_usage(0, 0))
    storage, proxy = _make_storage()
    monkeypatch.setattr(documents_module, "purge_stale_pending_documents", AsyncMock())

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.post(
        f"/api/v1/projects/{project.id}/documents/init",
        json={"filename": "01_Employer_Spec_Rev01.pdf", "size_bytes": 2000},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["upload_url"] == "https://up"
    assert body["token"] == "tok"
    assert body["document"]["status"] == "pending"
    assert body["document"]["doc_type"] == "Employer Technical Specifications"
    assert body["document"]["revision_number"] == 1
    assert body["document"]["retention"] == "persistent"
    proxy.create_signed_upload_url.assert_awaited_once()


def test_init_upload_tags_rfq_specific_file_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    session = _make_session()
    session.get = AsyncMock(return_value=project)
    session.execute = AsyncMock(return_value=_usage(0, 0))
    storage, _ = _make_storage()
    monkeypatch.setattr(documents_module, "purge_stale_pending_documents", AsyncMock())

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.post(
        f"/api/v1/projects/{project.id}/documents/init",
        json={"filename": "03_RFQ_Blower_Template.xlsx", "size_bytes": 2000},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["doc_type"] == "RFQ Template"
    assert body["document"]["retention"] == "transient"


def test_init_upload_rejects_bad_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    session = _make_session()
    session.get = AsyncMock(return_value=project)
    session.execute = AsyncMock(return_value=_usage(0, 0))
    storage, _ = _make_storage()
    monkeypatch.setattr(documents_module, "purge_stale_pending_documents", AsyncMock())

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.post(
        f"/api/v1/projects/{project.id}/documents/init",
        json={"filename": "malware.exe", "size_bytes": 2000},
    )
    assert response.status_code == 415


def test_init_upload_rejects_when_project_not_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    project = _make_project(uuid.uuid4())
    session = _make_session()
    session.get = AsyncMock(return_value=project)
    storage, _ = _make_storage()
    monkeypatch.setattr(documents_module, "purge_stale_pending_documents", AsyncMock())

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(uuid.uuid4())}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.post(
        f"/api/v1/projects/{project.id}/documents/init",
        json={"filename": "01_Spec.pdf", "size_bytes": 2000},
    )
    assert response.status_code == 404


def test_finalize_marks_processing_and_schedules(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    document = _make_document(project.id, status=DocumentStatus.PENDING)
    session = _make_session()
    session.get = AsyncMock(side_effect=[document, project])
    storage, proxy = _make_storage()
    proxy.info = AsyncMock(return_value={"size": 1000})
    scheduled = AsyncMock()
    monkeypatch.setattr(documents_module, "run_document_validation", scheduled)

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.post(f"/api/v1/documents/{document.id}/finalize")

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    scheduled.assert_awaited_once()


def test_finalize_missing_object_returns_400() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    document = _make_document(project.id, status=DocumentStatus.PENDING)
    session = _make_session()
    session.get = AsyncMock(side_effect=[document, project])
    storage, proxy = _make_storage()
    proxy.info = AsyncMock(side_effect=StorageException("not found"))

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.post(f"/api/v1/documents/{document.id}/finalize")
    assert response.status_code == 400


def test_finalize_oversized_object_fails_and_removes() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    document = _make_document(project.id, status=DocumentStatus.PENDING)
    session = _make_session()
    session.get = AsyncMock(side_effect=[document, project])
    storage, proxy = _make_storage()
    proxy.info = AsyncMock(return_value={"size": 10_000 * _MB})

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.post(f"/api/v1/documents/{document.id}/finalize")

    assert response.status_code == 413
    assert document.status == DocumentStatus.FAILED
    proxy.remove.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_finalize_conflict_when_not_pending() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    document = _make_document(project.id, status=DocumentStatus.READY)
    session = _make_session()
    session.get = AsyncMock(side_effect=[document, project])
    storage, _ = _make_storage()

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.post(f"/api/v1/documents/{document.id}/finalize")
    assert response.status_code == 409


def test_list_documents() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    document = _make_document(project.id)
    session = _make_session()
    session.get = AsyncMock(return_value=project)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [document]
    session.execute = AsyncMock(return_value=result)

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session

    client = TestClient(app)
    response = client.get(f"/api/v1/projects/{project.id}/documents")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_document_includes_download_url() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    document = _make_document(project.id, status=DocumentStatus.READY)
    session = _make_session()
    session.get = AsyncMock(side_effect=[document, project])
    storage, _ = _make_storage()

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.get(f"/api/v1/documents/{document.id}")
    assert response.status_code == 200
    assert response.json()["download_url"] == "https://download"


def test_patch_document_classification_sets_manual_and_recomputes_retention() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    document = _make_document(project.id, retention=RetentionPolicy.TRANSIENT)
    session = _make_session()
    session.get = AsyncMock(side_effect=[document, project])

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session

    client = TestClient(app)
    response = client.patch(f"/api/v1/documents/{document.id}", json={"doc_type": "Equipment List"})
    assert response.status_code == 200
    body = response.json()
    assert body["doc_type"] == "Equipment List"
    assert body["doc_type_source"] == "manual"
    assert body["retention"] == "persistent"  # Equipment List is a project-common doc


def test_delete_document_removes_object() -> None:
    owner = uuid.uuid4()
    project = _make_project(owner)
    document = _make_document(project.id)
    session = _make_session()
    session.get = AsyncMock(side_effect=[document, project])
    storage, proxy = _make_storage()

    app.dependency_overrides[get_current_user] = lambda: {"sub": str(owner)}
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage

    client = TestClient(app)
    response = client.delete(f"/api/v1/documents/{document.id}")
    assert response.status_code == 204
    session.delete.assert_awaited_once()
    proxy.remove.assert_awaited_once()
