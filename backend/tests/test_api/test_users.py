"""Tests for users routes, get_db dependency, and JWT auth helper."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import deps
from app.api.deps import get_db
from app.core import security
from app.core.security import get_current_user
from app.main import app

USER_ID = str(uuid4())


@pytest.fixture
def overridden_app() -> Iterator[tuple[TestClient, AsyncMock]]:
    """Provide a TestClient with get_db and get_current_user overridden."""
    db_mock = AsyncMock()
    db_mock.add = MagicMock()
    db_mock.flush = AsyncMock()

    async def _fake_get_db():
        yield db_mock

    def _fake_get_current_user():
        return {"sub": USER_ID}

    app.dependency_overrides[get_db] = _fake_get_db
    app.dependency_overrides[get_current_user] = _fake_get_current_user
    try:
        yield TestClient(app), db_mock
    finally:
        app.dependency_overrides.clear()


def test_get_my_profile_404_when_missing(overridden_app):
    test_client, db_mock = overridden_app
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db_mock.execute = AsyncMock(return_value=result_mock)

    resp = test_client.get("/users/me")
    assert resp.status_code == 404


def test_get_my_profile_returns_user(overridden_app):
    test_client, db_mock = overridden_app
    user_obj = MagicMock()
    user_obj.id = uuid4()
    user_obj.name = "Bob"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user_obj
    db_mock.execute = AsyncMock(return_value=result_mock)

    resp = test_client.get("/users/me")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Bob"


async def test_get_db_commits_on_success():
    """Exercise the happy-path of the get_db generator (commit + close)."""
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


async def test_get_db_rolls_back_on_exception():
    """Exercise the exception path (rollback + close, re-raise)."""
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


def test_get_current_user_decodes_valid_token():
    """Decode path returns the JWT payload."""
    fake_creds = MagicMock(credentials="fake.jwt.token")
    fake_payload = {"sub": USER_ID, "aud": "authenticated"}

    with (
        patch.object(security._jwks_client, "get_signing_key_from_jwt") as get_key,
        patch.object(security.jwt, "decode", return_value=fake_payload),
    ):
        get_key.return_value = MagicMock(key="fake-key")
        result = security.get_current_user(fake_creds)

    assert result == fake_payload


def test_get_current_user_raises_401_on_invalid_token():
    """InvalidTokenError must surface as HTTP 401."""
    fake_creds = MagicMock(credentials="fake.jwt.token")

    with (
        patch.object(security._jwks_client, "get_signing_key_from_jwt") as get_key,
        patch.object(security.jwt, "decode", side_effect=pyjwt.InvalidTokenError("bad")),
    ):
        get_key.return_value = MagicMock(key="fake-key")
        with pytest.raises(HTTPException) as exc:
            security.get_current_user(fake_creds)

    assert exc.value.status_code == 401
