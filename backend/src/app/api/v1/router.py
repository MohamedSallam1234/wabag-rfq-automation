"""Aggregated v1 API router."""

from fastapi import APIRouter

from app.api.v1.documents import router as documents_router
from app.api.v1.projects import router as projects_router

api_router = APIRouter()
api_router.include_router(projects_router)
api_router.include_router(documents_router)
