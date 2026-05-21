"""Async SQLAlchemy engine, session factory, and declarative base."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models."""

    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def ping_db() -> None:
    """Run a trivial query to confirm database connectivity (readiness probe).

    Raises:
        Exception: If a connection cannot be established or the query fails.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
