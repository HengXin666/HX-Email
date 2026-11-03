"""GitHub App Manifest 的 HTTP 装配: 四个端点, 一个可替换的传输层.

`github_manifest.py` 提供原语 (manifest 内容, state, code 兑换, 凭据落库), 这里把它们
组成端点并挂到 `/api/v1/router/github` 下.

只有回调不校验管理员: 浏览器从 github.com 跳回来时不一定带着本服务的登录态, 而一次性
state 已经证明这次流程是某个管理员发起的. 其余三个端点都要求管理员.

`default_transport` 是模块级函数而不是常量, 测试用它换掉真实网络. 生产走 `RequestsTransport`.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Annotated, Final
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from hx_email.api.dependencies import require_admin
from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import AuthenticatedUser
from hx_email.server.router.providers.impl import github_manifest
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    build_app_jwt,
    open_app_config,
)
from hx_email.server.router.providers.impl.github.github_http import (
    HttpTransport,
    RequestsTransport,
)
from hx_email.server.router.providers.impl.github_manifest import ManifestError

LOGGER: logging.Logger = logging.getLogger("hx_email.router.github.connect")
PREFIX: Final[str] = "/router/github"
MANIFEST_ACTION: Final[str] = "https://github.com/settings/apps/new"
GITHUB_KIND: Final[str] = "github"
INSTALLATIONS_PAGE: Final[int] = 100
LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})
REASON_TEXT: Final[dict[str, str]] = {
    "invalid_state": "授权已过期或被重复使用, 请重新点一次创建按钮",
    "conversion_failed": "向 GitHub 兑换凭据失败, 请重试",
    "conversion_incomplete": "GitHub 返回的凭据不完整",
    "encryption_unavailable": "服务端加密密钥不可用, 无法安全保存私钥",
    "save_failed": "凭据保存失败",
    "missing_code_or_state": "回调缺少必要参数",
}
CALLBACK_CSS: Final[str] = (
    "body{font-family:system-ui,sans-serif;max-width:34rem;margin:18vh auto;padding:0 1.5rem;"
    "color:#1f2328;line-height:1.7}h1{font-size:1.15rem;margin:0 0 .75rem}"
    "p{margin:.4rem 0;color:#57606a}"
)


def pick_base_url(settings: Settings, base_url: str, request: Request) -> str:
    """Resolve the public root GitHub will call back on.

    A user opening the console on localhost is normal during development, but GitHub's
    servers cannot reach localhost, so the address the browser used is a poor default.
    An explicitly configured public root wins; the request is only a last resort.
    """
    configured: str = str(getattr(settings, "public_base_url", "") or "")
    if configured:
        return configured.rstrip("/")
    if base_url:
        return base_url.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")


def ensure_public(base: str) -> None:
    """Reject a loopback root before GitHub does, with an actionable message."""
    if urlsplit(base).hostname in LOOPBACK_HOSTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "GitHub webhook 需要公网可达地址, 请设置环境变量 HX_EMAIL_PUBLIC_BASE_URL",
        )


def render_result(title: str, detail: str, ok: bool) -> HTMLResponse:
    """Self-contained result page: the callback must not depend on where the console is hosted."""
    body: str = (
        "<!doctype html><meta charset=utf-8>"
        f"<title>{title}</title><style>{CALLBACK_CSS}</style>"
        f"<h1>{title}</h1><p>{detail}</p>"
    )
    return HTMLResponse(body, status_code=200 if ok else 400, headers={"Cache-Control": "no-store"})


def default_transport() -> HttpTransport:
    """The real transport; tests monkeypatch this to a fake."""
    return RequestsTransport()


def _ensure_github_instance(settings: Settings, user_id: int) -> int:
    """One instance per account is enough; reuse it so repeated clicks do not pile up rows."""
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT id FROM messaging_instances WHERE user_id = ? AND kind = ? ORDER BY id LIMIT 1",
            (user_id, GITHUB_KIND),
        ).fetchone()
        if row is not None:
            return int(row["id"])
        cursor: sqlite3.Cursor = connection.execute(
            "INSERT INTO messaging_instances (user_id, kind, name) VALUES (?, ?, ?)",
            (user_id, GITHUB_KIND, "GitHub"),
        )
        connection.commit()
        return int(cursor.lastrowid or 0)


def _config_for(settings: Settings, instance_id: int) -> GitHubAppConfig:
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT config_encrypted FROM messaging_instances WHERE id = ? AND kind = ?",
            (instance_id, GITHUB_KIND),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown GitHub instance")
    sealed: str = str(row["config_encrypted"] or "")
    if not sealed:
        raise HTTPException(status.HTTP_409_CONFLICT, "GitHub App is not connected yet")
    try:
        return open_app_config(settings, sealed)
    except (ValueError, OSError) as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Stored GitHub App config is unreadable"
        ) from error


def _jwt(config: GitHubAppConfig) -> str:
    """RS256 App JWT from the decrypted key; the key is not retained afterwards."""
    return build_app_jwt(config.private_key_pem, config.jwt_issuer(), github_manifest.utc_now())


def _installation_ids(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []
    out: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        account: object = item.get("account")
        login: str = ""
        if isinstance(account, dict):
            login = str(account.get("login") or "")
        out.append({"id": item.get("id"), "account": login})
    return out


# GitHub App 一键创建与秘密字段只写不读的决策
# 决策记录: .agents/notes/implemented/feature/2026-11-03-github-app-manifest-flow.md
def register_github_connect_routes(router: APIRouter, settings: Settings) -> None:
    """Mount the four manifest-flow endpoints on ``router``."""

    def failure(reason: str) -> HTMLResponse:
        return render_result(
            "GitHub 授权失败",
            REASON_TEXT.get(reason, f"未知原因: {reason}"),
            False,
        )

    @router.get(f"{PREFIX}/manifest")
    def start_manifest(
        request: Request,
        base_url: str = Query(default="", max_length=500),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Mint a one-time state and hand the browser the manifest to POST to GitHub."""
        user: AuthenticatedUser = require_admin(settings, authorization)
        user_id: int = int(user.id)
        base: str = pick_base_url(settings, base_url, request)
        ensure_public(base)
        instance_id: int = _ensure_github_instance(settings, user_id)
        now = github_manifest.utc_now()
        state: str = github_manifest.create_state()
        expires = github_manifest.save_state(settings, state, instance_id, now)
        manifest = github_manifest.build_manifest(
            base, github_manifest.create_name_suffix(), instance_id
        )
        return {
            "action": f"{MANIFEST_ACTION}?state={state}",
            "state": state,
            "expires_at": expires.strftime(github_manifest.TIME_FORMAT),
            "instance_id": instance_id,
            "manifest": manifest,
        }

    @router.get(f"{PREFIX}/callback")
    def receive_callback(
        code: str = Query(default=""), state: str = Query(default="")
    ) -> HTMLResponse:
        """Consume the state, spend the code, store the App. No admin check by design."""
        if not code or not state:
            return failure("missing_code_or_state")
        try:
            github_manifest.ensure_encryption_ready(settings)
        except ManifestError as error:
            return failure(error.reason)
        # The state is consumed before the code is spent: a code works once, so letting
        # the same state retry after a failed conversion would just fail again.
        try:
            instance_id: int = github_manifest.consume_state(
                settings, state, github_manifest.utc_now()
            )
        except ManifestError as error:
            return failure(error.reason)
        try:
            body = github_manifest.convert_manifest(code, default_transport())
        except ManifestError as error:
            return failure(error.reason)
        try:
            config: GitHubAppConfig = github_manifest.config_from_conversion(body)
            github_manifest.store_app_config(settings, instance_id, config)
        except (KeyError, TypeError, ValueError, OSError) as error:
            LOGGER.warning("cannot store GitHub App config: %s", error)
            return failure("save_failed")
        return render_result(
            f"GitHub App 已创建: {config.app_slug}",
            "可以关闭本页, 回到 HX-Email 的 Messaging 页面点「验证连接」",
            True,
        )

    @router.post(f"{PREFIX}/verify")
    def verify_app(
        instance_id: int = Body(embed=True),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Sign a JWT with the stored key and prove it against the real GitHub API."""
        require_admin(settings, authorization)
        config: GitHubAppConfig = _config_for(settings, instance_id)
        transport: HttpTransport = default_transport()
        try:
            token: str = _jwt(config)
        except (ValueError, TypeError) as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Stored private key is unusable"
            ) from error
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hx-email-router",
        }
        app_response = transport.request("GET", "https://api.github.com/app", headers, None)
        if app_response.status != 200:
            return {"verified": False, "app_config": github_manifest.public_app_summary(config)}
        listed = transport.request(
            "GET",
            f"https://api.github.com/app/installations?per_page={INSTALLATIONS_PAGE}",
            headers,
            None,
        )
        return {
            "verified": True,
            "app": app_response.as_dict().get("slug", config.app_slug),
            "installations": _installation_ids(listed.body),
            "app_config": github_manifest.public_app_summary(config),
        }

    @router.post(f"{PREFIX}/installations/{{installation_id}}/attach")
    def attach_installation(
        installation_id: int,
        instance_id: int = Body(embed=True),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Bind one installation to an instance after confirming GitHub reports it."""
        require_admin(settings, authorization)
        config: GitHubAppConfig = _config_for(settings, instance_id)
        transport: HttpTransport = default_transport()
        token: str = _jwt(config)
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hx-email-router",
        }
        response = transport.request(
            "GET", f"https://api.github.com/app/installations/{installation_id}", headers, None
        )
        if response.status != 200:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "GitHub does not report this installation"
            )
        account: object = response.as_dict().get("account")
        login: str = str(account.get("login") or "") if isinstance(account, dict) else ""
        with connect(settings) as connection:
            connection.execute(
                "UPDATE messaging_instances SET name = ?, updated_at = datetime('now') "
                "WHERE id = ? AND kind = ?",
                (f"GitHub ({login})" if login else "GitHub", instance_id, GITHUB_KIND),
            )
            connection.commit()
        return {"attached": True, "installation": {"id": installation_id, "account": login}}
