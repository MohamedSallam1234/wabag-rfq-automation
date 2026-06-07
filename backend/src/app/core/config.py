"""Application settings loaded from environment variables."""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["local", "dev", "test", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_SYSTEM_PROMPT_FILE = Path(__file__).resolve().parents[1] / "agents" / "llm" / "system_prompt.md"


def _default_system_rules() -> list[str]:
    """Load the F-04 AI Operating Rules from the bundled system_prompt.md file."""
    text = _SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


class Settings(BaseSettings):
    """Typed configuration sourced from dotenv files and the process environment."""

    model_config = SettingsConfigDict(
        # APP_ENV selects which env-specific dotenv file to load. It is read from the OS
        # environment (not from Settings) on purpose: this runs *before* Settings exists, so
        # the selector cannot come from pydantic. In non-local deploys APP_ENV must be a real
        # environment variable — one written *inside* .env.<env> can't select its own file.
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
    # Consumed only by the initial migration to create the least-privilege app_user role.
    # Optional so the running app (which connects via DATABASE_URL) boots without it; the
    # migration raises a clear error if it is needed but unset.
    APP_USER_PASSWORD: SecretStr = Field(default=SecretStr(""), repr=False)

    # Supabase storage
    SUPABASE_URL: str
    SUPABASE_SECRET_KEY: str = Field(
        ...,
        repr=False,
        description="Server-side secret key used by the Storage client.",
    )

    # CORS
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Document storage / upload (Supabase Storage)
    SUPABASE_STORAGE_BUCKET: str = "rfq-documents"
    # Cap on the incoming request *body* size (a guardrail, not a business quota). This can be
    # generous because born-digital PDFs are slimmed to Markdown and the heavy original is
    # discarded — only MAX_STORED_ARTIFACT_MB ever reaches the bucket.
    MAX_UPLOAD_SIZE_MB: int = 300
    # Cap on the final *stored* artifact (the .md for PDFs, the original for other types).
    # Kept at 50 to match the Supabase free-tier bucket file_size_limit.
    MAX_STORED_ARTIFACT_MB: int = 50
    SIGNED_DOWNLOAD_URL_TTL_S: int = 600
    STORAGE_CLIENT_TIMEOUT_S: int = 120
    ALLOWED_UPLOAD_EXTENSIONS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [".pdf", ".docx", ".xlsx", ".xls"],
    )

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

    @field_validator("ALLOWED_UPLOAD_EXTENSIONS", mode="before")
    @classmethod
    def _split_allowed_extensions(cls, value: str | list[str]) -> list[str]:
        """Parse a comma-separated env value into normalized lowercase, dotted extensions."""
        items = value.split(",") if isinstance(value, str) else value
        normalized: list[str] = []
        for item in items:
            ext = item.strip().lower()
            if not ext:
                continue
            normalized.append(ext if ext.startswith(".") else f".{ext}")
        return normalized


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()


settings = get_settings()
