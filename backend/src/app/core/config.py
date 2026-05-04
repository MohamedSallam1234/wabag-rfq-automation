from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings.

    Args:
        BaseSettings

    Returns:
        void
    """

    APP_ENV: str = "local"
    DATABASE_URL: str
    MIGRATION_DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    model_config = SettingsConfigDict(
        env_file=f".env.{__import__('os').getenv('APP_ENV', 'local')}",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
