import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, str]]:
    """Docs."""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": str(u.id), "name": u.name} for u in users]


@router.get("/me")
async def get_my_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, str]:
    """Docs."""
    user_id = uuid.UUID(auth["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Profile not found")
    return {"id": str(user.id), "name": user.name}
