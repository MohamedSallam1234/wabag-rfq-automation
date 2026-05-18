"""Shared FastAPI dependencies (database session, LLM router, etc.)."""

from collections.abc import AsyncGenerator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm.router import LLMRouter
from app.core.database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, committing on success and rolling back on error.

    Yields:
        An open :class:`AsyncSession` bound to the request lifecycle.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def get_router(request: Request) -> LLMRouter:
    """Return the process-wide :class:`LLMRouter` attached to the app at startup."""
    return cast(LLMRouter, request.app.state.llm_router)
