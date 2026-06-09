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


def test_get_router_returns_app_state() -> None:
    """get_router returns the LLM router attached to app.state."""
    sentinel = object()
    request = MagicMock()
    request.app.state.llm_router = sentinel
    assert deps.get_router(request) is sentinel


def test_get_storage_returns_app_state() -> None:
    """get_storage returns the storage client attached to app.state."""
    sentinel = object()
    request = MagicMock()
    request.app.state.storage = sentinel
    assert deps.get_storage(request) is sentinel


async def test_load_project_or_404_returns_found() -> None:
    project = MagicMock()
    db = MagicMock()
    db.get = AsyncMock(return_value=project)
    assert await deps.load_project_or_404(db, uuid4()) is project


async def test_load_project_or_404_raises_when_missing() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await deps.load_project_or_404(db, uuid4())
    assert exc.value.status_code == 404


async def test_load_document_or_404_returns_found() -> None:
    document = MagicMock()
    db = MagicMock()
    db.get = AsyncMock(return_value=document)
    assert await deps.load_document_or_404(db, uuid4()) is document


async def test_load_document_or_404_raises_when_missing() -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await deps.load_document_or_404(db, uuid4())
    assert exc.value.status_code == 404
