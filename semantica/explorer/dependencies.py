"""
Semantica Explorer : FastAPI Dependencies

Provides ``Depends()``-compatible callables for injecting the
current ``GraphSession`` and ``ConnectionManager`` into route handlers,
and for enforcing API-key authentication on protected routes.
"""

import hmac
import os
from typing import Optional

from fastapi import Request, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

from .session import GraphSession
from .ws import ConnectionManager

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_expected_api_key() -> Optional[str]:
    """Read the configured API key from the environment on every call.

    Read fresh (not cached) so tests and ops tooling can rotate the key
    without restarting the process.
    """
    return os.environ.get("SEMANTICA_API_KEY") or None


def anonymous_access_allowed() -> bool:
    return os.environ.get("SEMANTICA_ALLOW_ANONYMOUS", "").strip().lower() == "true"


def is_valid_api_key(candidate: Optional[str]) -> bool:
    """Return True if *candidate* matches the configured key, or if the
    server has explicitly opted into anonymous access."""
    if anonymous_access_allowed():
        return True
    expected = get_expected_api_key()
    if not expected:
        return False
    return bool(candidate) and hmac.compare_digest(candidate, expected)


def require_auth(api_key: Optional[str] = Security(_api_key_header)) -> None:
    """Dependency enforcing the ``X-API-Key`` header on protected routes.

    Every Explorer/API router (except health/info/static assets) should be
    mounted with ``dependencies=[Depends(require_auth)]``. If
    SEMANTICA_API_KEY is unset, requests are refused with 503 rather than
    silently served unauthenticated — SEMANTICA_ALLOW_ANONYMOUS=true opts
    into that explicitly for local development.
    """
    if anonymous_access_allowed():
        return
    expected = get_expected_api_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Server is not configured for authentication. Set the "
                "SEMANTICA_API_KEY environment variable, or explicitly opt "
                "into unauthenticated access (development only) with "
                "SEMANTICA_ALLOW_ANONYMOUS=true."
            ),
        )
    if not api_key or not hmac.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Send it as the X-API-Key header.",
        )


def get_session(request: Request) -> GraphSession:
    """Retrieve the GraphSession stored on ``app.state``."""
    if not hasattr(request.app.state, "session") or request.app.state.session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GraphSession not initialized."
        )
    return request.app.state.session


def get_ws_manager(request: Request) -> ConnectionManager:
    """Retrieve the ConnectionManager stored on ``app.state``."""
    if not hasattr(request.app.state, "ws_manager") or request.app.state.ws_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WebSocket manager not initialized.",
        )
    return request.app.state.ws_manager
