from fastapi import HTTPException, status

from hx_email.config import Settings
from hx_email.server.auth import AuthenticatedUser, authenticate_token


def bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return token


def require_user(settings: Settings, authorization: str | None) -> AuthenticatedUser:
    token = bearer_token(authorization)
    user = authenticate_token(settings, token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user


def require_admin(settings: Settings, authorization: str | None) -> AuthenticatedUser:
    user = require_user(settings, authorization)
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user
