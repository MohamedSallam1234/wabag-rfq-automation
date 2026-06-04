"""CRUD-lite endpoints for projects (open endpoints — no authentication)."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, load_project_or_404
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: DbSession) -> Project:
    """Create a project."""
    project = Project(**payload.model_dump())
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(db: DbSession) -> Sequence[Project]:
    """List all projects, newest first."""
    stmt = select(Project).order_by(Project.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, db: DbSession) -> Project:
    """Fetch a project by id (404 if missing)."""
    return await load_project_or_404(db, project_id)
