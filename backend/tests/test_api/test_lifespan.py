"""Tests for the FastAPI lifespan wiring (OpenRouter + Supabase storage)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app import main


async def test_lifespan_sets_and_closes_storage() -> None:
    fake_supabase = MagicMock()
    fake_supabase.storage.session.aclose = AsyncMock()

    open_router_cm = MagicMock()
    open_router_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    open_router_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(main, "OpenRouter", return_value=open_router_cm),
        patch.object(main, "build_router", return_value=MagicMock()),
        patch.object(main, "create_supabase_client", AsyncMock(return_value=fake_supabase)),
        patch.object(main, "recover_stuck_processing_documents", AsyncMock()) as recover,
    ):
        async with main.lifespan(main.app):
            assert main.app.state.storage is fake_supabase.storage
            # Let the recovery task run before shutdown cancels it.
            await asyncio.sleep(0)

    recover.assert_called_once()
    fake_supabase.storage.session.aclose.assert_awaited_once()
