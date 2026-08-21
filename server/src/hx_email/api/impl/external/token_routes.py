"""External API token-status and patrol routes."""

from typing import Annotated

from fastapi import FastAPI, Header, Query
from pydantic import BaseModel

from hx_email.config import Settings
from hx_email.server.external_api import (
    get_token_status,
    refresh_group_tokens,
    require_api_key,
)
from hx_email.server.mail.verification import MailboxProvider


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


class TokenRefreshRequest(BaseModel):
    group_id: int = 0


def register_external_token_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    @app.get("/api/external/token-status")
    def ext_token_status(
        user_id: int = Query(default=1, ge=1),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        return external_response(True, data=get_token_status(settings, user_id))

    @app.post("/api/external/token/refresh")
    def ext_token_refresh(
        payload: TokenRefreshRequest,
        user_id: int = Query(default=1, ge=1),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_api_key(settings, authorization)
        if payload.group_id < 0:
            return external_response(
                False,
                code="INVALID_GROUP",
                message="group_id must be 0 (ungrouped) or a positive group id",
                error_code="INVALID_GROUP",
            )
        result = refresh_group_tokens(settings, user_id, payload.group_id, mailbox_provider)
        if "error" in result:
            return external_response(
                False,
                code="INVALID_GROUP",
                message=str(result["error"]),
                error_code="INVALID_GROUP",
            )
        return external_response(True, data=result)
