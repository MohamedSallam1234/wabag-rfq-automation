"""Application settings loaded from environment variables."""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["local", "dev", "test", "prod"]
JwtAlgorithm = Literal["ES256", "RS256"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_SYSTEM_PROMPT_FILE = Path(__file__).resolve().parents[1] / "agents" / "llm" / "system_prompt.md"


def _default_jwt_algorithms() -> list[JwtAlgorithm]:
    """Return the default Supabase JWT signing algorithms."""
    return ["ES256", "RS256"]


def _default_system_rules() -> list[str]:
    """Load the F-04 AI Operating Rules from the bundled system_prompt.md file."""
    text = _SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


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

    # LLM (OpenRouter — Claude Opus 4.7 primary, Sonnet 4.6 fallback)
    OPENROUTER_API_KEY: SecretStr = Field(default=SecretStr(""), repr=False)
    PRIMARY_MODEL: str = "anthropic/claude-opus-4.7"
    FALLBACK_MODEL: str = "anthropic/claude-sonnet-4.6"
    LLM_TIMEOUT_S: float = 60.0
    SYSTEM_RULES: Annotated[list[str], NoDecode] = Field(
        default_factory=_default_system_rules,
    )

    @field_validator("SYSTEM_RULES", mode="before")
    @classmethod
    def _split_system_rules(cls, value: str | list[str]) -> list[str]:
        """Turn a pipe-separated env value into a list of rules (rules may contain commas)."""
        if isinstance(value, str):
            return [rule.strip() for rule in value.split("|") if rule.strip()]
        return value

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
