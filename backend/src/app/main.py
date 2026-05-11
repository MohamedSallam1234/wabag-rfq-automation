"""FastAPI app factory: lifespan-managed shared httpx client + LLM router wiring."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException

from app.agents.llm.router import LLMFatalError, LLMRouter, LLMTransientError, build_router
from app.api.deps import get_router
from app.core.config import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create one process-wide :class:`httpx.AsyncClient` and :class:`LLMRouter`."""
    settings = get_settings()
    async with httpx.AsyncClient() as http_client:
        app.state.http_client = http_client
        app.state.llm_router = build_router(settings, http_client)
        yield


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
        msg: str = "Say hello in 5 words.",
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

    return app


app = create_app()
