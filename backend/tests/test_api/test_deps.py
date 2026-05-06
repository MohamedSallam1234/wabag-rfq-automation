"""Tests for shared API dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
