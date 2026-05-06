"""Application settings loaded from environment variables."""

import os
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["local", "dev", "test", "prod"]
JwtAlgorithm = Literal["ES256", "RS256"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _default_jwt_algorithms() -> list[JwtAlgorithm]:
    """Return the default Supabase JWT signing algorithms."""
    return ["ES256", "RS256"]


class Settings(BaseSettings):
    """Typed configuration sourced from dotenv files and the process environment."""

    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{os.getenv('APP_ENV', 'local')}"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_ENV: AppEnv = "local"
    DEBUG: bool = False
    LOG_LEVEL: LogLevel = "INFO"

    # Database
    DATABASE_URL: str = Field(..., description="SQLAlchemy async DSN for the app database")
    MIGRATION_DATABASE_URL: str = Field(..., description="SQLAlchemy DSN for Alembic migrations")

    # Supabase auth/storage
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str = Field(..., repr=False)
    SUPABASE_SERVICE_ROLE_KEY: str = Field(..., repr=False)
    SUPABASE_JWT_SECRET: str = Field(
        default="",
        repr=False,
        description="Legacy symmetric JWT secret; runtime auth verifies Supabase JWKS.",
    )

    # JWT verification
    JWT_ALGORITHMS: Annotated[list[JwtAlgorithm], NoDecode] = Field(
        default_factory=_default_jwt_algorithms,
    )
    JWT_AUDIENCE: str = "authenticated"

    # CORS
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Turn a comma-separated env value into a list of origins."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("JWT_ALGORITHMS", mode="before")
    @classmethod
    def _split_jwt_algorithms(cls, value: str | list[str]) -> list[str]:
        """Turn a comma-separated env value into a list of accepted algorithms."""
        if isinstance(value, str):
            return [algorithm.strip() for algorithm in value.split(",") if algorithm.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()


settings = get_settings()
