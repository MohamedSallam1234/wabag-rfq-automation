"""Tests for backend environment configuration."""

from app.core.config import Settings, get_settings


def test_settings_parses_comma_separated_lists() -> None:
    """Comma-separated env values should load without JSON list syntax."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/app",
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_ANON_KEY="anon",
        SUPABASE_SERVICE_ROLE_KEY="service",
        CORS_ORIGINS="http://localhost:3000, http://localhost:5173,,",
        JWT_ALGORITHMS="ES256, RS256",
    )

    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]
    assert settings.JWT_ALGORITHMS == ["ES256", "RS256"]


def test_settings_cache_returns_singleton(monkeypatch) -> None:
    """Settings are cached per process until explicitly cleared by tests."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/app")
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://user:pass@localhost/app")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")

    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()

    try:
        assert first is second
    finally:
        get_settings.cache_clear()
