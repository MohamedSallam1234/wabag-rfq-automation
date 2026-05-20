"""Pydantic request/response schemas for projects."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Payload to create a project."""

    name: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    consultant: str | None = Field(default=None, max_length=255)
    project_number: str | None = Field(default=None, max_length=128)
    capacity_m3d: int | None = None


class ProjectRead(BaseModel):
    """Project as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location: str | None
    client: str | None
    consultant: str | None
    project_number: str | None
    capacity_m3d: int | None
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
