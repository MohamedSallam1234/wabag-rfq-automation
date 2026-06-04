"""Tests for backend environment configuration."""

from app.core.config import Settings, get_settings


def test_app_user_password_is_hidden_secret() -> None:
    """APP_USER_PASSWORD loads as a SecretStr (consumed by the migration) and never reprs."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
        APP_USER_PASSWORD="role-secret",  # pragma: allowlist secret
    )

    assert settings.APP_USER_PASSWORD.get_secret_value() == "role-secret"
    assert "role-secret" not in repr(settings)


def test_app_user_password_is_optional() -> None:
    """The app boots without APP_USER_PASSWORD (only the migration requires it)."""
    field = Settings.model_fields["APP_USER_PASSWORD"]
    assert not field.is_required()
    assert field.default.get_secret_value() == ""


def test_settings_parses_comma_separated_lists() -> None:
    """Comma-separated env values should load without JSON list syntax."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
        OPENROUTER_API_KEY="testing-api-key",  # pragma: allowlist secret
        CORS_ORIGINS="http://localhost:3000, http://localhost:5173,,",
    )

    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]


def test_settings_normalizes_allowed_extensions() -> None:
    """ALLOWED_UPLOAD_EXTENSIONS parses to lowercase, dot-prefixed values."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
        OPENROUTER_API_KEY="testing-api-key",  # pragma: allowlist secret
        ALLOWED_UPLOAD_EXTENSIONS="PDF, .docx ,xlsx",
    )

    assert settings.ALLOWED_UPLOAD_EXTENSIONS == [".pdf", ".docx", ".xlsx"]


def test_settings_parses_pipe_separated_system_rules() -> None:
    """SYSTEM_RULES env var should split on pipes (rules contain commas)."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
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
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
        OPENROUTER_API_KEY="testing-api-key",  # pragma: allowlist secret
    )

    assert len(settings.SYSTEM_RULES) > 0
    assert any("RFQ" in rule for rule in settings.SYSTEM_RULES)


def test_settings_storage_defaults() -> None:
    """Storage/upload settings default sensibly; removed auth/hardening config is gone."""
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/app",  # pragma: allowlist secret
        MIGRATION_DATABASE_URL="postgresql://user:pass@localhost/app",  # pragma: allowlist secret
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SECRET_KEY="service",  # pragma: allowlist secret
    )

    assert settings.MAX_UPLOAD_SIZE_MB == 50
    assert settings.SUPABASE_STORAGE_BUCKET == "rfq-documents"
    assert settings.SIGNED_DOWNLOAD_URL_TTL_S == 600
    assert settings.ALLOWED_UPLOAD_EXTENSIONS == [".pdf", ".docx", ".xlsx", ".xls"]
    assert not hasattr(settings, "AV_SCAN_ENABLED")  # removed with the validation hardening
    assert not hasattr(settings, "JWT_ALGORITHMS")  # removed with authentication


def test_settings_cache_returns_singleton(monkeypatch) -> None:
    """Settings are cached per process until explicitly cleared by tests."""
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://u:p@lo/app"
    )  # pragma: allowlist secret
    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL", "postgresql://u:p@l/ap"
    )  # pragma: allowlist secret
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "service")  # pragma: allowlist secret
    monkeypatch.setenv("OPENROUTER_API_KEY", "testing-api-key")  # pragma: allowlist secret

    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()

    try:
        assert first is second
    finally:
        get_settings.cache_clear()
