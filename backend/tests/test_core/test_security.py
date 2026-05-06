"""Tests for JWT security helpers."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.core import security


def test_get_current_user_decodes_valid_token() -> None:
    """Decode path returns the JWT payload."""
    user_id = str(uuid4())
    fake_creds = MagicMock(credentials="fake.jwt.token")
    fake_payload = {"sub": user_id, "aud": "authenticated"}

    with (
        patch.object(security._jwks_client, "get_signing_key_from_jwt") as get_key,
        patch.object(security.jwt, "decode", return_value=fake_payload),
    ):
        get_key.return_value = MagicMock(key="fake-key")
        result = security.get_current_user(fake_creds)

    assert result == fake_payload


def test_get_current_user_raises_401_on_invalid_token() -> None:
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
