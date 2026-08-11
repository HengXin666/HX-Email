from fastapi import HTTPException, status

from hx_email.config import Settings
from hx_email.server.auth import AuthenticatedUser, authenticate_token
from hx_email.server.external_api.impl.auth import validate_api_key


def bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def require_user(settings: Settings, authorization: str | None) -> AuthenticatedUser:
    token = bearer_token(authorization)
    user = authenticate_token(settings, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(settings: Settings, authorization: str | None) -> AuthenticatedUser:
    user = require_user(settings, authorization)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


def require_admin_or_sync_key(
    settings: Settings, authorization: str | None
) -> AuthenticatedUser | str:
    """Accept either an admin session token or the master's external API key.

    Master-slave sync peers authenticate with the Bearer token configured on the
    slave; allow the master's own external API key so a slave can pull a snapshot
    and push local changes without a browser session.
    """
    token = bearer_token(authorization)
    user = authenticate_token(settings, token)
    if user is not None:
        if not user.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
        return user
    if validate_api_key(settings, token):
        return token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )
