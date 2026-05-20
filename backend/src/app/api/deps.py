"""Shared FastAPI dependencies (database session, LLM router, storage, authz)."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from storage3 import AsyncStorageClient

from app.agents.llm.router import LLMRouter
from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.models.project import Project


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


def get_storage(request: Request) -> AsyncStorageClient:
    """Return the process-wide Supabase storage client attached to the app at startup."""
    return cast(AsyncStorageClient, request.app.state.storage)


def current_user_id(user: dict[str, Any]) -> uuid.UUID:
    """Extract the Supabase user id (UUID) from decoded JWT claims."""
    return uuid.UUID(str(user["sub"]))


async def load_owned_project(
    db: AsyncSession, project_id: uuid.UUID, owner_id: uuid.UUID
) -> Project:
    """Load a project owned by ``owner_id`` or raise 404 (also hides others' projects).

    Raises:
        HTTPException: 404 if the project is absent or owned by another user.
    """
    project = await db.get(Project, project_id)
    if project is None or project.owner_id != owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


async def load_owned_document(
    db: AsyncSession, document_id: uuid.UUID, owner_id: uuid.UUID
) -> Document:
    """Load a document whose parent project is owned by ``owner_id`` or raise 404.

    Raises:
        HTTPException: 404 if the document is absent or not owned by this user.
    """
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    project = await db.get(Project, document.project_id)
    if project is None or project.owner_id != owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document
