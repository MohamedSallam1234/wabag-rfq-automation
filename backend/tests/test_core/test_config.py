"""Tests for backend environment configuration."""

from app.core.config import Settings, get_settings


def test_settings_parses_comma_separated_lists() -> None:
    """Comma-separated env values should load without JSON list syntax."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="anon",
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
        OPENROUTER_API_KEY="testing-api-key",  # pragma: allowlist secret
        CORS_ORIGINS="http://localhost:3000, http://localhost:5173,,",
        JWT_ALGORITHMS="ES256, RS256",
    )

    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]
    assert settings.JWT_ALGORITHMS == ["ES256", "RS256"]


def test_settings_parses_pipe_separated_system_rules() -> None:
    """SYSTEM_RULES env var should split on pipes (rules contain commas)."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="anon",
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
        OPENROUTER_API_KEY="testing-api-key",  # pragma: allowlist secret
        SYSTEM_RULES="Rule one, with a comma.|Rule two.|  | Rule three.",
    )

    assert settings.SYSTEM_RULES == [
        "Rule one, with a comma.",
        "Rule two.",
        "Rule three.",
    ]


def test_settings_uses_default_system_rules_when_unset() -> None:
    """If SYSTEM_RULES is not provided, the baked-in defaults are used."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="anon",
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
        OPENROUTER_API_KEY="testing-api-key",  # pragma: allowlist secret
    )

    assert len(settings.SYSTEM_RULES) > 0
    assert any("RFQ" in rule for rule in settings.SYSTEM_RULES)


def test_settings_document_safety_defaults() -> None:
    """New validation-hardening / recovery settings default sensibly; dead one is gone."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
    )

    assert settings.RECOVERY_SWEEP_INTERVAL_S == 300
    assert settings.MAX_DECOMPRESSED_SIZE_MB == 500
    assert settings.MAX_COMPRESSION_RATIO == 100
    assert settings.MAX_ARCHIVE_ENTRIES == 10000
    assert settings.AV_SCAN_ENABLED is False
    assert not hasattr(settings, "SIGNED_UPLOAD_URL_TTL_S")  # removed (un-wireable dead config)


def test_settings_cache_returns_singleton(monkeypatch) -> None:
    """Settings are cached per process until explicitly cleared by tests."""
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://u:p@lo/app"
    )  # pragma: allowlist secret
    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL", "postgresql://u:p@l/ap"
    )  # pragma: allowlist secret
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "service")  # pragma: allowlist secret
    monkeypatch.setenv("OPENROUTER_API_KEY", "testing-api-key")  # pragma: allowlist secret

    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()

    try:
        assert first is second
    finally:
        get_settings.cache_clear()
