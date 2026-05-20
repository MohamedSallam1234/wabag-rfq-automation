"""FastAPI app factory: lifespan-managed OpenRouter SDK client + LLM router wiring."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from openrouter import OpenRouter

from app.agents.llm.router import LLMFatalError, LLMRouter, LLMTransientError, build_router
from app.api.deps import get_router
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.supabase import create_supabase_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the process-wide OpenRouter SDK client, LLM router, and Supabase client."""
    settings = get_settings()
    async with OpenRouter(
        api_key=settings.OPENROUTER_API_KEY.get_secret_value(),
    ) as open_router:
        app.state.open_router = open_router
        app.state.llm_router = build_router(settings, open_router)
        supabase = await create_supabase_client(settings)
        app.state.supabase = supabase
        app.state.storage = supabase.storage
        try:
            yield
        finally:
            await supabase.storage.session.aclose()


def create_app() -> FastAPI:
    """Create the FastAPI app factory pattern."""
    app = FastAPI(
        title="LinkDrop",
        description="A personal URL shortener with tags and analytics.",
        version="0.1.0",
        contact={"name": "Mohamed Sallam", "email": "Sallamm733@gmail.com"},
        license_info={"name": "MIT"},
        lifespan=lifespan,
    )

    @app.get("/health", tags=["meta"])
    def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:  # noqa: B008
        return {"status": "ok", "env": settings.APP_ENV}

    @app.get("/llm/ping", tags=["meta"])
    async def llm_ping(
        msg: str = "Which model are you? and what is your role?",
        llm: LLMRouter = Depends(get_router),  # noqa: B008
    ) -> dict[str, str]:
        """Smoke-test the LLM router: round-trip a single user message."""
        try:
            response = await llm.ask(user_message=msg)
            return {"response": response}
        except LLMTransientError as exc:
            raise HTTPException(
                status_code=503, detail=f"LLM temporarily unavailable: {exc}"
            ) from exc
        except LLMFatalError as exc:
            raise HTTPException(status_code=400, detail=f"LLM request failed: {exc}") from exc

    app.include_router(api_router)
    return app


app = create_app()
