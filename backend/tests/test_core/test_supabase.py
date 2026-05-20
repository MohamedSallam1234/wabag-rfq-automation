"""Tests for the Supabase client factory."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import get_settings
from app.core.supabase import create_supabase_client


async def test_create_supabase_client_passes_storage_timeout() -> None:
    settings = get_settings()
    fake_client = MagicMock()
    with patch("app.core.supabase.acreate_client", AsyncMock(return_value=fake_client)) as create:
        result = await create_supabase_client(settings)

    assert result is fake_client
    create.assert_awaited_once()
    _, kwargs = create.call_args
    assert kwargs["options"].storage_client_timeout == settings.STORAGE_CLIENT_TIMEOUT_S
