"""Google OAuth start and callback routes."""

import html
import json
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response

from hx_email.api.dependencies import require_user
from hx_email.api.impl.mail.oauth.config_routes import google_oauth_config
from hx_email.config import Settings
from hx_email.server.mail.google_oauth import complete_google_oauth, prepare_google_oauth
from hx_email.server.settings_service import get_setting


def google_callback_html(message: str, success: bool) -> str:
    color: str = "#3fb950" if success else "#f85149"
    payload: str = json.dumps(
        {"type": "hx-google-oauth", "success": success, "message": message},
        ensure_ascii=True,
    ).replace("<", "\\u003c")
    safe_message: str = html.escape(message)
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Google OAuth</title>"
        "</head><body style='font-family:sans-serif;background:#0d1117;color:#c9d1d9;"
        "display:grid;place-items:center;min-height:100vh;margin:0'>"
        f"<main><h1 style='color:{color};font-size:20px'>{safe_message}</h1>"
        "<p>此窗口将自动关闭。</p></main>"
        f"<script>window.opener?.postMessage({payload}, '*');"
        "setTimeout(() => window.close(), 700);</script></body></html>"
    )


def register_google_authorization_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/email-accounts/{account_id}/google-oauth/prepare")
    def prepare_authorization(
        account_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        user = require_user(settings, authorization)
        config = google_oauth_config(settings)
        try:
            return prepare_google_oauth(
                settings,
                user.id,
                account_id,
                str(config["client_id"]),
                get_setting(settings, "google_oauth_client_secret", ""),
                str(config["redirect_uri"]),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/google-oauth/callback")
    def google_oauth_callback(
        code: str = "",
        state: str = "",
        error: str = "",
        error_description: str = "",
    ) -> Response:
        if error:
            message: str = f"Google 授权失败: {error_description or error}"
            return Response(
                google_callback_html(message, False),
                status_code=400,
                media_type="text/html; charset=utf-8",
            )
        if not code or not state:
            message = "Google 授权回调缺少 code 或 state"
            return Response(
                google_callback_html(message, False),
                status_code=400,
                media_type="text/html; charset=utf-8",
            )
        try:
            result = complete_google_oauth(settings, code, state)
        except (ValueError, RuntimeError) as oauth_error:
            return Response(
                google_callback_html(str(oauth_error), False),
                status_code=400,
                media_type="text/html; charset=utf-8",
            )
        return Response(
            google_callback_html(f"{result.email} 授权成功", True),
            media_type="text/html; charset=utf-8",
        )
