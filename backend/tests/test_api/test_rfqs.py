"""Tests for the RFQ generation endpoint (multipart template upload + one fused LLM call)."""

import io
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.agents.llm.router import LLMFatalError, LLMTransientError
from app.api.deps import get_db, get_router, get_storage
from app.main import app
from app.models.project import Project

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_VALID_JSON = json.dumps(
    {
        "equipment_tag": "B-100",
        "header": {"Project": "Kohafa"},
        "sections": [
            {
                "title": "Process",
                "fields": [
                    {
                        "field": "Capacity",
                        "value": 860,
                        "unit": "m3/hr",
                        "confidence": 0.9,
                        "source_ref": "04",
                        "status": "extracted",
                    },
                    {"field": "Head", "value": None, "status": "tbd", "confidence": 0.0},
                ],
            }
        ],
    }
)


# --------------------------------------------------------------------------- #
# Fixtures / fakes
# --------------------------------------------------------------------------- #
def _xlsx_template_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Blower"
    sheet.append(["Field", "Value"])
    sheet.append(["Capacity", ""])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def _fake_refresh(instance: object, *_: object, **__: object) -> None:
    now = datetime.now(UTC)
    for attr in ("created_at", "updated_at"):
        if getattr(instance, attr, None) is None:
            setattr(instance, attr, now)


def _make_project() -> Project:
    now = datetime.now(UTC)
    return Project(id=uuid.uuid4(), name="P", created_at=now, updated_at=now)


def _make_session(project: Project | None, sources: list[object]) -> MagicMock:
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock(side_effect=_fake_refresh)
    session.get = AsyncMock(return_value=project)
    result = MagicMock()
    result.scalars.return_value.all.return_value = sources
    session.execute = AsyncMock(return_value=result)
    return session


def _make_storage() -> tuple[MagicMock, MagicMock]:
    storage = MagicMock()
    proxy = MagicMock()
    proxy.download = AsyncMock(return_value=b"## Sheet\nsource markdown")
    proxy.upload = AsyncMock(return_value={"path": "p"})
    storage.from_ = MagicMock(return_value=proxy)
    return storage, proxy


class _FakeLLM:
    """Stand-in for LLMRouter exposing the async ``ask`` coroutine the generator calls."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, str | None]] = []

    async def ask(self, user_message: str, task_instructions: str | None = None) -> str:
        self.calls.append((user_message, task_instructions))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _source() -> SimpleNamespace:
    return SimpleNamespace(
        storage_path="projects/p/documents/d/01_Spec.pdf.md",
        original_filename="01_Spec.pdf",
        doc_type="Employer Technical Specifications",
    )


def _override(session: MagicMock, storage: MagicMock, llm: _FakeLLM) -> None:
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_router] = lambda: llm


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _post(client: TestClient, project_id: uuid.UUID, *, equipment: str | None = "aeration blower"):
    files = {"file": ("05_RFQ_Blower.xlsx", _xlsx_template_bytes(), _XLSX_MIME)}
    data = {"equipment": equipment} if equipment is not None else {}
    return client.post(f"/api/v1/projects/{project_id}/rfqs", files=files, data=data)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_generate_rfq_returns_201_and_persists_xlsx() -> None:
    project = _make_project()
    session = _make_session(project, [_source()])
    storage, proxy = _make_storage()
    llm = _FakeLLM(response=_VALID_JSON)
    _override(session, storage, llm)

    client = TestClient(app)
    response = _post(client, project.id)

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["content_type"] == _XLSX_MIME
    assert body["document"]["original_filename"] == "RFQ_aeration_blower.xlsx"
    assert body["summary"] == {"fields_total": 2, "extracted": 1, "conflict": 0, "tbd": 1}

    # The generated .xlsx is stored under the per-document key with the xlsx content type.
    proxy.upload.assert_awaited_once()
    stored_path, stored_bytes, opts = proxy.upload.call_args.args
    assert stored_path.startswith(f"projects/{project.id}/documents/")
    assert stored_path.endswith("RFQ_aeration_blower.xlsx")
    assert opts == {"content-type": _XLSX_MIME}
    assert stored_bytes.startswith(b"PK\x03\x04")

    # The uploaded template was NOT persisted; only sources were downloaded (one per source doc).
    proxy.download.assert_awaited_once()
    session.add.assert_called_once()
    assert "aeration blower" in llm.calls[0][0]


def test_generate_rfq_fans_out_one_call_per_source_plus_merge() -> None:
    project = _make_project()
    sources = [_source(), _source(), _source()]
    session = _make_session(project, sources)
    storage, proxy = _make_storage()
    llm = _FakeLLM(response=_VALID_JSON)
    _override(session, storage, llm)

    client = TestClient(app)
    response = _post(client, project.id)

    assert response.status_code == 201
    # 3 source documents → 3 extraction calls + 1 merge call; each source downloaded once.
    assert len(llm.calls) == len(sources) + 1
    assert proxy.download.await_count == len(sources)


def test_generate_rfq_missing_project_returns_404() -> None:
    session = _make_session(None, [])
    storage, proxy = _make_storage()
    llm = _FakeLLM(response=_VALID_JSON)
    _override(session, storage, llm)

    client = TestClient(app)
    response = _post(client, uuid.uuid4())

    assert response.status_code == 404
    proxy.upload.assert_not_awaited()
    assert llm.calls == []


def test_generate_rfq_no_source_documents_returns_422() -> None:
    project = _make_project()
    session = _make_session(project, [])
    storage, proxy = _make_storage()
    llm = _FakeLLM(response=_VALID_JSON)
    _override(session, storage, llm)

    client = TestClient(app)
    response = _post(client, project.id)

    assert response.status_code == 422
    assert llm.calls == []
    proxy.upload.assert_not_awaited()


def test_generate_rfq_unsupported_template_type_returns_415() -> None:
    project = _make_project()
    session = _make_session(project, [_source()])
    storage, proxy = _make_storage()
    llm = _FakeLLM(response=_VALID_JSON)
    _override(session, storage, llm)

    client = TestClient(app)
    response = client.post(
        f"/api/v1/projects/{project.id}/rfqs",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"equipment": "aeration blower"},
    )

    assert response.status_code == 415
    proxy.upload.assert_not_awaited()


def test_generate_rfq_missing_equipment_field_returns_422() -> None:
    project = _make_project()
    session = _make_session(project, [_source()])
    storage, _ = _make_storage()
    llm = _FakeLLM(response=_VALID_JSON)
    _override(session, storage, llm)

    client = TestClient(app)
    response = _post(client, project.id, equipment=None)

    assert response.status_code == 422


def test_generate_rfq_invalid_llm_json_returns_502() -> None:
    project = _make_project()
    session = _make_session(project, [_source()])
    storage, proxy = _make_storage()
    llm = _FakeLLM(response="not json at all")
    _override(session, storage, llm)

    client = TestClient(app)
    response = _post(client, project.id)

    assert response.status_code == 502
    proxy.upload.assert_not_awaited()


def test_generate_rfq_llm_transient_returns_503() -> None:
    project = _make_project()
    session = _make_session(project, [_source()])
    storage, _ = _make_storage()
    llm = _FakeLLM(error=LLMTransientError("down"))
    _override(session, storage, llm)

    client = TestClient(app)
    response = _post(client, project.id)

    assert response.status_code == 503


def test_generate_rfq_llm_fatal_returns_400() -> None:
    project = _make_project()
    session = _make_session(project, [_source()])
    storage, _ = _make_storage()
    llm = _FakeLLM(error=LLMFatalError("bad request"))
    _override(session, storage, llm)

    client = TestClient(app)
    response = _post(client, project.id)

    assert response.status_code == 400
