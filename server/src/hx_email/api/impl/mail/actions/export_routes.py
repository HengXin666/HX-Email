"""Export routes for email accounts with token-based authorization."""

from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import ExportSelected, ExportVerify
from hx_email.config import Settings
from hx_email.server.mail.impl.accounts import (
    export_all_accounts_text,
    export_selected_accounts_text,
    validate_export_token,
    verify_export_password,
)


def _extract_export_token(settings: Settings, authorization: str | None) -> str:
    """Extract and validate the X-Export-Token header."""
    token: str = ""
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value
    if not token or not validate_export_token(settings, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing export token",
        )
    return token


def register_export_routes(app: FastAPI, settings: Settings) -> None:
    @app.post("/export/verify")
    def export_verify(
        payload: ExportVerify,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        verify_token = verify_export_password(settings, user.id, payload.password)
        if verify_token is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
        return {"success": True, "verify_token": verify_token}

    @app.get("/email-accounts/export")
    def export_all_accounts(
        authorization: Annotated[str | None, Header()] = None,
        x_export_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        user = require_user(settings, authorization)
        _validate_export_header(settings, x_export_token)
        text = export_all_accounts_text(settings, user.id)
        headers = {
            "Content-Disposition": 'attachment; filename="hx-email-accounts.txt"',
        }
        return Response(text, media_type="text/plain; charset=utf-8", headers=headers)

    @app.post("/email-accounts/export-selected")
    def export_selected_accounts(
        payload: ExportSelected,
        authorization: Annotated[str | None, Header()] = None,
        x_export_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        user = require_user(settings, authorization)
        _validate_export_header(settings, x_export_token)
        if payload.verify_token and not validate_export_token(settings, payload.verify_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid verify token",
            )
        text = export_selected_accounts_text(settings, user.id, payload.group_ids)
        headers = {
            "Content-Disposition": 'attachment; filename="hx-email-accounts.txt"',
        }
        return Response(text, media_type="text/plain; charset=utf-8", headers=headers)


def _validate_export_header(settings: Settings, x_export_token: str | None) -> None:
    """Validate the X-Export-Token header."""
    if not x_export_token or not validate_export_token(settings, x_export_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Export-Token header",
        )
