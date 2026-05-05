"""Application settings loaded from environment variables."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration sourced from ``.env.<APP_ENV>`` and the process env."""

    APP_ENV: str = "local"
    DATABASE_URL: str
    MIGRATION_DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str = ""  # Legacy — kept for reference; auth uses JWKS, not this secret

    model_config = SettingsConfigDict(
        env_file=f".env.{os.getenv('APP_ENV', 'local')}",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()


settings = get_settings()
