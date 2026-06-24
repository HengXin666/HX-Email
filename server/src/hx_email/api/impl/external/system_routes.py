"""External API system routes: health, capabilities, account-status."""

from typing import Annotated

from fastapi import FastAPI, Header, Query

from hx_email.config import Settings
from hx_email.server.external_api import (
    get_account_status,
    get_capabilities,
    get_health,
    require_api_key,
)


def external_response(
    success: bool,
    data: object = None,
    code: str = "OK",
    message: str = "success",
    error_code: str | None = None,
) -> dict[str, object]:
    """Build consistent external API response wrapper."""
    if success:
        return {"success": True, "code": code, "message": message, "data": data}
    return {"success": False, "code": error_code or "ERROR", "message": message, "data": None}


def register_external_system_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/api/external/health")
    def ext_health(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        return external_response(True, data=get_health(settings))

    @app.get("/api/external/capabilities")
    def ext_capabilities(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        return external_response(True, data=get_capabilities(settings))

    @app.get("/api/external/account-status")
    def ext_account_status(
        email: str = Query(...),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        return external_response(True, data=get_account_status(settings, email))
