"""Google OAuth application configuration routes."""

from typing import Annotated

from fastapi import APIRouter, Header
from pydantic import BaseModel

from hx_email.api.dependencies import require_admin, require_user
from hx_email.config import Settings
from hx_email.server.settings_service import get_setting, set_setting


class GoogleOAuthConfigWrite(BaseModel):
    client_id: str
    client_secret: str = ""
    redirect_uri: str


def google_oauth_config(settings: Settings) -> dict[str, object]:
    secret: str = get_setting(settings, "google_oauth_client_secret", "")
    return {
        "client_id": get_setting(settings, "google_oauth_client_id", ""),
        "redirect_uri": get_setting(settings, "google_oauth_redirect_uri", ""),
        "has_client_secret": bool(secret),
    }


def register_google_oauth_config_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/google-oauth/config")
    def get_config(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return google_oauth_config(settings)

    @router.put("/google-oauth/config")
    def put_config(
        payload: GoogleOAuthConfigWrite,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_admin(settings, authorization)
        set_setting(settings, "google_oauth_client_id", payload.client_id.strip())
        set_setting(settings, "google_oauth_redirect_uri", payload.redirect_uri.strip())
        if payload.client_secret.strip():
            set_setting(settings, "google_oauth_client_secret", payload.client_secret.strip())
        return google_oauth_config(settings)
