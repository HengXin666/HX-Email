"""Caller identity for the gateway: a router API key or a web console session.

Machine callers (MCP clients, scripts) use ``hxr_`` keys bound to one user; the web
console keeps its session token. Hold/resume and key management accept only the
session, so a leaked key can neither lift a breaker nor mint more keys.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from hx_email.api.dependencies import bearer_token, require_user
from hx_email.config import Settings
from hx_email.server.auth import authenticate_token
from hx_email.server.gateway.api_keys import KEY_PREFIX, verify_key


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def caller_user_id(settings: Settings, authorization: str | None) -> int:
    """User id from ``Authorization: Bearer <hxr_ key | session token>``."""
    token: str = bearer_token(authorization)
    if token.startswith(KEY_PREFIX):
        user_id: int | None = verify_key(settings, token)
        if user_id is None:
            raise unauthorized("Invalid or revoked router API key")
        return user_id
    user = authenticate_token(settings, token)
    if user is None:
        raise unauthorized("Invalid token")
    return int(user.id)


def session_user_id(settings: Settings, authorization: str | None) -> int:
    """Web console session only; router keys are refused here on purpose."""
    token: str = bearer_token(authorization)
    if token.startswith(KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint needs the web console session, not a router API key",
        )
    return int(require_user(settings, authorization).id)
