from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import bearer_token, require_admin, require_user
from hx_email.api.schemas import Credentials, RegistrationSettingUpdate
from hx_email.config import Settings
from hx_email.server.auth import (
    authenticate_token,
    create_session,
    login,
    register_user,
    registration_enabled,
    revoke_session,
    set_registration_enabled,
    update_credentials,
)


def register_auth_routes(app: FastAPI, settings: Settings) -> None:
    @app.post("/auth/login")
    def log_in(credentials: Credentials) -> dict[str, object]:
        session = login(settings, credentials.username, credentials.password)
        if session is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        user, access_token = session
        return {
            "access_token": access_token,
            "user": {"id": user.id, "username": user.username, "is_admin": user.is_admin},
        }

    @app.put("/auth/me/credentials")
    def update_my_credentials(
        credentials: Credentials,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, dict[str, object]]:
        user = require_user(settings, authorization)
        updated_user = update_credentials(
            settings,
            user,
            credentials.username,
            credentials.password,
        )
        return {
            "user": {
                "id": updated_user.id,
                "username": updated_user.username,
                "is_admin": updated_user.is_admin,
            }
        }

    @app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def log_out(authorization: Annotated[str | None, Header()] = None) -> None:
        token = bearer_token(authorization)
        if authenticate_token(settings, token) is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        revoke_session(settings, token)

    @app.post("/auth/register", status_code=status.HTTP_201_CREATED)
    def register(credentials: Credentials) -> dict[str, object]:
        if not registration_enabled(settings):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Registration disabled"
            )
        user = register_user(settings, credentials.username, credentials.password)
        return {
            "access_token": create_session(settings, user),
            "user": {"id": user.id, "username": user.username, "is_admin": user.is_admin},
        }

    @app.put("/admin/settings/registration")
    def update_registration_setting(
        payload: RegistrationSettingUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        require_admin(settings, authorization)
        return {"registration_enabled": set_registration_enabled(settings, payload.enabled)}
