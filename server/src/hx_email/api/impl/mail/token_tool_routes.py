from typing import Annotated
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import (
    TokenToolConfigWrite,
    TokenToolExchange,
    TokenToolPrepare,
    TokenToolSave,
)
from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.impl.accounts.account_transfer import (
    create_oauth_account,
    save_oauth_credentials,
)
from hx_email.server.mail.impl.oauth_tool import (
    OAuthConfig,
    exchange_code,
    parse_callback_url,
    peek_flow,
    prepare_oauth,
)


class TokenAccount(BaseModel):
    id: int
    email: str
    status: str
    provider: str


DEFAULT_SCOPE: str = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
DEFAULT_REDIRECT_URI: str = "http://localhost:8000/token-tool/callback"


def register_token_tool_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/token-tool/config")
    def get_token_tool_config(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return {"success": True, "data": load_config(settings)}

    @router.post("/token-tool/config")
    def save_token_tool_config(
        payload: TokenToolConfigWrite,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        save_config(settings, payload)
        return {"success": True, "data": load_config(settings)}

    @router.get("/token-tool/accounts")
    def get_token_tool_accounts(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return {
            "success": True,
            "data": [account.model_dump() for account in list_token_accounts(settings, user.id)],
        }

    @router.post("/token-tool/prepare")
    def prepare_token_tool(
        payload: TokenToolPrepare,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        try:
            return build_prepare_response(
                {
                    "client_id": payload.client_id,
                    "redirect_uri": payload.redirect_uri,
                    "scope": payload.scope,
                    "tenant": payload.tenant,
                    "prompt_consent": payload.prompt_consent,
                }
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/token-tool/prepare-from-config")
    def prepare_token_tool_from_config(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        try:
            return build_prepare_response(load_config(settings))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/token-tool/callback")
    def handle_token_tool_callback(
        code: str = "",
        state: str = "",
        error: str = "",
        error_description: str = "",
    ) -> Response:
        if error:
            body = callback_html(f"授权失败: {error} {error_description}", is_error=True)
            return Response(body, media_type="text/html; charset=utf-8")
        if not code or not state:
            body = callback_html("回调缺少 code 或 state 参数", is_error=True)
            return Response(body, media_type="text/html; charset=utf-8")
        flow = peek_flow(state)
        if flow is None:
            body = callback_html("授权流程已过期, 请重新生成授权链接", is_error=True)
            return Response(body, media_type="text/html; charset=utf-8")
        body = callback_html("授权成功, 请回到 Token 工具页面继续换取并保存 refresh_token")
        return Response(body, media_type="text/html; charset=utf-8")

    @router.post("/token-tool/exchange")
    def exchange_token_tool(
        payload: TokenToolExchange,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        try:
            code, state = resolve_exchange_input(payload)
            result = exchange_code(code, state)
            return {"success": True, "data": result}
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise HTTPException(status_code=400, detail=detail) from error
        except URLError as error:
            raise HTTPException(status_code=502, detail=str(error.reason)) from error

    @router.post("/token-tool/save")
    def save_token_tool(
        payload: TokenToolSave,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if payload.mode == "create":
            if not payload.email:
                raise HTTPException(status_code=422, detail="Email is required")
            account_id = create_oauth_account(
                settings,
                user.id,
                payload.email,
                payload.client_id,
                payload.refresh_token,
            )
            return {"success": True, "data": {"account_id": account_id, "email": payload.email}}
        if payload.mode == "update":
            if payload.account_id is None:
                raise HTTPException(status_code=422, detail="Account id is required")
            saved = save_oauth_credentials(
                settings,
                user.id,
                payload.account_id,
                payload.client_id,
                payload.refresh_token,
            )
            if not saved:
                raise HTTPException(status_code=404, detail="Email account not found")
            return {
                "success": True,
                "data": {"account_id": payload.account_id, "email": payload.email},
            }
        raise HTTPException(status_code=422, detail="Mode must be create or update")


def build_prepare_response(config: dict[str, object]) -> dict[str, object]:
    result = prepare_oauth(
        OAuthConfig(
            client_id=str(config.get("client_id") or ""),
            redirect_uri=str(config.get("redirect_uri") or DEFAULT_REDIRECT_URI),
            scope=str(config.get("scope") or DEFAULT_SCOPE),
            tenant=str(config.get("tenant") or "consumers"),
            prompt_consent=bool(config.get("prompt_consent")),
        )
    )
    return {
        "success": True,
        "data": {
            "authorize_url": result["authorization_url"],
            "authorization_url": result["authorization_url"],
            "state": result["state"],
            "scope": result["scope"],
        },
    }


def resolve_exchange_input(payload: TokenToolExchange) -> tuple[str, str]:
    if payload.callback_url:
        return parse_callback_url(payload.callback_url)
    if not payload.code:
        raise ValueError("Code is required")
    if not payload.state:
        raise ValueError("State is required")
    return payload.code, payload.state


def load_config(settings: Settings) -> dict[str, object]:
    return {
        "client_id": get_setting(settings, "oauth_tool_client_id", ""),
        "redirect_uri": get_setting(settings, "oauth_tool_redirect_uri", DEFAULT_REDIRECT_URI),
        "scope": get_setting(settings, "oauth_tool_scope", DEFAULT_SCOPE),
        "tenant": get_setting(settings, "oauth_tool_tenant", "consumers"),
        "prompt_consent": get_setting(settings, "oauth_tool_prompt_consent", "true") == "true",
    }


def save_config(settings: Settings, payload: TokenToolConfigWrite) -> None:
    set_setting(settings, "oauth_tool_client_id", payload.client_id)
    set_setting(settings, "oauth_tool_redirect_uri", payload.redirect_uri or DEFAULT_REDIRECT_URI)
    set_setting(settings, "oauth_tool_scope", payload.scope or DEFAULT_SCOPE)
    set_setting(settings, "oauth_tool_tenant", payload.tenant or "consumers")
    set_setting(
        settings, "oauth_tool_prompt_consent", "true" if payload.prompt_consent else "false"
    )


def get_setting(settings: Settings, key: str, default: str) -> str:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT value FROM system_settings WHERE key = ?",
            (key,),
        ).fetchone()
    return str(row["value"]) if row is not None else default


def set_setting(settings: Settings, key: str, value: str) -> None:
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO system_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def list_token_accounts(settings: Settings, user_id: int) -> list[TokenAccount]:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, primary_address, status, provider
            FROM email_accounts
            WHERE user_id = ? AND provider IN ('outlook', 'gmail')
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()
    return [
        TokenAccount(
            id=row["id"],
            email=row["primary_address"],
            status=row["status"],
            provider=row["provider"],
        )
        for row in rows
    ]


def callback_html(message: str, is_error: bool = False) -> str:
    color = "#f85149" if is_error else "#3fb950"
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>OAuth Callback</title>"
        "</head><body style='font-family:sans-serif;background:#0d1117;color:#c9d1d9;"
        "display:grid;place-items:center;min-height:100vh;margin:0'>"
        f"<main style='max-width:520px'><h1 style='color:{color};font-size:20px'>"
        f"{message}</h1><p>可以关闭此页面。</p></main></body></html>"
    )
