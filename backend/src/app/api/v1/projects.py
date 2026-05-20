"""CRUD-lite endpoints for projects (owner-scoped)."""

import uuid
from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, get_db, load_owned_project
from app.core.security import get_current_user
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, user: CurrentUser, db: DbSession) -> Project:
    """Create a project owned by the current user."""
    project = Project(owner_id=current_user_id(user), **payload.model_dump())
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(user: CurrentUser, db: DbSession) -> Sequence[Project]:
    """List the current user's projects, newest first."""
    stmt = (
        select(Project)
        .where(Project.owner_id == current_user_id(user))
        .order_by(Project.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().all()


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Project:
    """Fetch one of the current user's projects (404 if not owned)."""
    return await load_owned_project(db, project_id, current_user_id(user))
