"""FastAPI app factory: lifespan-managed OpenRouter SDK client + LLM router wiring."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from openrouter import OpenRouter

from app.agents.llm.router import LLMFatalError, LLMRouter, LLMTransientError, build_router
from app.api.deps import get_router
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import ping_db
from app.core.supabase import create_supabase_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the process-wide OpenRouter SDK client, LLM router, and Supabase client."""
    settings = get_settings()
    # Apply the configured log level (so LOG_LEVEL actually takes effect) and surface the
    # resolved environment on the first log line — if a deploy loaded the wrong .env file
    # (e.g. APP_ENV was not set in the OS environment), this will read "local" in production.
    logging.basicConfig(level=settings.LOG_LEVEL)
    logger.info("starting up: APP_ENV=%s, DEBUG=%s", settings.APP_ENV, settings.DEBUG)
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
        title="WABAG RFQ Automation",
        description="Backend for RFQ document intake, classification, and generation.",
        version="0.1.0",
        contact={"name": "Mohamed Sallam", "email": "Sallamm733@gmail.com"},
        license_info={"name": "MIT"},
        lifespan=lifespan,
    )

    @app.get("/health", tags=["meta"])
    def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
        """Liveness probe: the process is up (does not check dependencies)."""
        return {"status": "ok", "env": settings.APP_ENV}

    @app.get("/ready", tags=["meta"])
    async def ready() -> dict[str, str]:
        """Readiness probe: the database is reachable (storage is wired at startup)."""
        try:
            await asyncio.wait_for(ping_db(), timeout=5)
        except Exception as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database not ready") from exc
        return {"status": "ready"}

    @app.get("/llm/ping", tags=["meta"])
    async def llm_ping(
        llm: Annotated[LLMRouter, Depends(get_router)],
        msg: str = "Which model are you? and what is your role?",
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
