"""Supabase async client factory (secret key) for storage operations.

This factory is intended to be called **once** from the FastAPI ``lifespan`` and the
resulting :class:`AsyncClient` stored on ``app.state`` — a single instance shared
across all requests via the ``get_storage`` dependency (a lifecycle-scoped
singleton, mirroring how the OpenRouter client is wired). A lifespan-managed
instance, rather than a module-level global, is used deliberately: the underlying
httpx ``AsyncClient`` must be created on the running event loop and closed on
shutdown.

Storage uses the secret key (server-side, bypasses storage RLS —
authorization is enforced in the API layer). The storage HTTP timeout is raised
above storage3's short default so large objects can be streamed during background
validation.
"""

from supabase import AsyncClient, AsyncClientOptions, acreate_client

from app.core.config import Settings


async def create_supabase_client(settings: Settings) -> AsyncClient:
    """Create a secret-key Supabase async client with a storage-friendly timeout.

    Call once from the app lifespan; close ``client.storage.session`` on shutdown.

    Args:
        settings: Application settings (Supabase URL/key and storage timeout).

    Returns:
        A connected :class:`AsyncClient`.
    """
    return await acreate_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SECRET_KEY,
        options=AsyncClientOptions(storage_client_timeout=settings.STORAGE_CLIENT_TIMEOUT_S),
    )
