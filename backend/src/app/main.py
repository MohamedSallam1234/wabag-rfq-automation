from fastapi import Depends, FastAPI

from app.core.config import Settings, get_settings


def create_app() -> FastAPI:
    """Create the FastAPI app factory pattern."""
    app = FastAPI(
        title="LinkDrop",
        description="A personal URL shortener with tags and analytics.",
        version="0.1.0",
        contact={"name": "Mohamed Sallam", "email": "Sallamm733@gmail.com"},
        license_info={"name": "MIT"},
    )

    @app.get("/health", tags=["meta"])
    def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:  # noqa: B008
        return {"status": "ok", "env": settings.APP_ENV}

    return app


app = create_app()
