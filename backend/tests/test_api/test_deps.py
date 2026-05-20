"""Tests for shared API dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import deps


async def test_get_db_commits_on_success() -> None:
    """Exercise the happy-path of the get_db generator."""
    fake_session = MagicMock()
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()
    fake_session.close = AsyncMock()

    with patch.object(deps, "AsyncSessionLocal", return_value=fake_session):
        gen = deps.get_db()
        yielded = await gen.__anext__()
        assert yielded is fake_session
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    fake_session.commit.assert_awaited_once()
    fake_session.close.assert_awaited_once()
    fake_session.rollback.assert_not_awaited()


async def test_get_db_rolls_back_on_exception() -> None:
    """Exercise the exception path."""
    fake_session = MagicMock()
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()
    fake_session.close = AsyncMock()

    with patch.object(deps, "AsyncSessionLocal", return_value=fake_session):
        gen = deps.get_db()
        await gen.__anext__()
        with pytest.raises(ValueError, match="boom"):
            await gen.athrow(ValueError("boom"))

    fake_session.rollback.assert_awaited_once()
    fake_session.close.assert_awaited_once()
    fake_session.commit.assert_not_awaited()


def test_get_storage_returns_app_state() -> None:
    """get_storage returns the storage client attached to app.state."""
    sentinel = object()
    request = MagicMock()
    request.app.state.storage = sentinel
    assert deps.get_storage(request) is sentinel


def test_current_user_id_parses_sub() -> None:
    """current_user_id parses the JWT 'sub' claim into a UUID."""
    user_id = uuid4()
    assert deps.current_user_id({"sub": str(user_id)}) == user_id


async def test_load_owned_project_returns_owned() -> None:
    owner = uuid4()
    project = MagicMock(owner_id=owner)
    db = MagicMock()
    db.get = AsyncMock(return_value=project)
    assert await deps.load_owned_project(db, uuid4(), owner) is project


async def test_load_owned_project_404_when_missing() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await deps.load_owned_project(db, uuid4(), uuid4())
    assert exc.value.status_code == 404


async def test_load_owned_project_404_when_not_owned() -> None:
    project = MagicMock(owner_id=uuid4())
    db = MagicMock()
    db.get = AsyncMock(return_value=project)
    with pytest.raises(HTTPException) as exc:
        await deps.load_owned_project(db, uuid4(), uuid4())
    assert exc.value.status_code == 404


async def test_load_owned_document_returns_owned() -> None:
    owner = uuid4()
    document = MagicMock(project_id=uuid4())
    project = MagicMock(owner_id=owner)
    db = MagicMock()
    db.get = AsyncMock(side_effect=[document, project])
    assert await deps.load_owned_document(db, uuid4(), owner) is document


async def test_load_owned_document_404_when_doc_missing() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await deps.load_owned_document(db, uuid4(), uuid4())
    assert exc.value.status_code == 404


async def test_load_owned_document_404_when_not_owned() -> None:
    document = MagicMock(project_id=uuid4())
    project = MagicMock(owner_id=uuid4())
    db = MagicMock()
    db.get = AsyncMock(side_effect=[document, project])
    with pytest.raises(HTTPException) as exc:
        await deps.load_owned_document(db, uuid4(), uuid4())
    assert exc.value.status_code == 404
