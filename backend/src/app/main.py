"""FastAPI app factory: lifespan-managed OpenRouter SDK client + LLM router wiring."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from openrouter import OpenRouter
from storage3 import AsyncStorageClient

from app.agents.llm.router import LLMFatalError, LLMRouter, LLMTransientError, build_router
from app.api.deps import get_router, get_storage
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import ping_db
from app.core.supabase import create_supabase_client
from app.services.ingestion.upload import run_recovery_loop


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
        # Periodically re-drive documents stuck in `processing` (crash/restart or a
        # transient validation failure left for retry). Runs off the boot path so a
        # slow/unreachable storage layer never blocks startup; cancelled on shutdown.
        recovery_task = asyncio.create_task(run_recovery_loop(supabase.storage, settings=settings))
        app.state.recovery_task = recovery_task
        try:
            yield
        finally:
            recovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await recovery_task
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
    def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:  # noqa: B008
        """Liveness probe: the process is up (does not check dependencies)."""
        return {"status": "ok", "env": settings.APP_ENV}

    @app.get("/ready", tags=["meta"])
    async def ready(
        storage: AsyncStorageClient = Depends(get_storage),  # noqa: B008
    ) -> dict[str, str]:
        """Readiness probe: the database is reachable and the storage client is wired."""
        try:
            await ping_db()
        except Exception as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database not ready") from exc
        if storage is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "storage not ready")
        return {"status": "ready"}

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
