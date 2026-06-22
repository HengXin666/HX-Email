from typing import Annotated

from fastapi import Body, FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from hx_email.auth import (
    AuthenticatedUser,
    authenticate_token,
    create_session,
    login,
    register_user,
    registration_enabled,
    revoke_session,
    set_registration_enabled,
    update_credentials,
)
from hx_email.config import Settings
from hx_email.usable_emails import add_usable_email, list_usable_emails


class Credentials(BaseModel):
    username: str
    password: str


class RegistrationSettingUpdate(BaseModel):
    enabled: bool


class UsableEmailCreate(BaseModel):
    address: str
    label: str = ""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="HX Email")

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "hx-email"}

    @app.post("/auth/login")
    def log_in(credentials: Credentials) -> dict[str, object]:
        session = login(settings, credentials.username, credentials.password)
        if session is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        user, access_token = session
        return {
            "access_token": access_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin,
            },
        }

    def bearer_token(authorization: str | None) -> str:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
        return token

    def require_user(authorization: str | None) -> AuthenticatedUser:
        token = bearer_token(authorization)
        user = authenticate_token(settings, token)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user

    def require_admin(authorization: str | None) -> AuthenticatedUser:
        user = require_user(authorization)
        if not user.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
        return user

    @app.put("/auth/me/credentials")
    def update_my_credentials(
        credentials: Credentials,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, dict[str, object]]:
        user = require_user(authorization)
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration disabled")

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
        require_admin(authorization)
        return {"registration_enabled": set_registration_enabled(settings, payload.enabled)}

    @app.post("/usable-emails", status_code=status.HTTP_201_CREATED)
    def create_usable_email(
        payload: UsableEmailCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(authorization)
        usable_email = add_usable_email(settings, user.id, payload.address, payload.label)
        return {"id": usable_email.id, "address": usable_email.address, "label": usable_email.label}

    @app.get("/usable-emails")
    def get_usable_emails(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(authorization)
        return {
            "usable_emails": [
                {"id": usable_email.id, "address": usable_email.address, "label": usable_email.label}
                for usable_email in list_usable_emails(settings, user.id)
            ]
        }

    return app


app = create_app()
