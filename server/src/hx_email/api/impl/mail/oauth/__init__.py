"""Google OAuth route registration."""

from fastapi import APIRouter

from hx_email.api.impl.mail.oauth.authorization_routes import (
    register_google_authorization_routes,
)
from hx_email.api.impl.mail.oauth.config_routes import register_google_oauth_config_routes
from hx_email.config import Settings

__all__ = ["register_google_oauth_routes"]


def register_google_oauth_routes(router: APIRouter, settings: Settings) -> None:
    register_google_oauth_config_routes(router, settings)
    register_google_authorization_routes(router, settings)
