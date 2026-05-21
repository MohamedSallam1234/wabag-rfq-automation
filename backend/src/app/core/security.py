"""Security primitives: Supabase JWT verification via JWKS."""

import logging
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger(__name__)

bearer = HTTPBearer()

# JWKS client fetches and caches Supabase's public keys automatically
_jwks_client = PyJWKClient(
    f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json",
    cache_keys=True,
    max_cached_keys=16,
    cache_jwk_set=True,
    lifespan=300,  # refresh every 5 min
)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> dict[str, Any]:
    """Resolve the current authenticated user from a Supabase JWT.

    Args:
        creds: Bearer credentials extracted from the ``Authorization`` header.

    Returns:
        The decoded JWT payload (claims).

    Raises:
        HTTPException: 401 if the token is missing, expired, or otherwise invalid.
    """
    token = creds.credentials
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=settings.JWT_ALGORITHMS,
            audience=settings.JWT_AUDIENCE,
        )
    except jwt.InvalidTokenError as e:
        logger.debug("JWT verification failed: %s", e)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from e
