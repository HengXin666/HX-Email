"""Short-lived Google OAuth PKCE flow bound to one local account.

Two flow shapes are supported:

- Account-bound: created for an existing Gmail account; the callback verifies
  the authorized Google email matches the account's primary address before
  saving credentials.
- Accountless: created without any email input; the callback reads the email
  from Google's userinfo endpoint and creates (or updates) the matching Gmail
  account automatically.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.google_oauth.impl.account_sync import (
    save_credentials_by_email,
    update_account_credentials,
)
from hx_email.server.mail.google_oauth.impl.tokens import (
    GOOGLE_MAIL_SCOPE,
    exchange_google_code,
    fetch_google_email,
)

GOOGLE_AUTHORIZE_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
FLOW_TTL_SECONDS: int = 20 * 60
FLOW_STATUS_PENDING: str = "pending"
FLOW_STATUS_DONE: str = "done"
FLOW_STATUS_ERROR: str = "error"

_FLOW_STORE: dict[str, dict[str, object]] = {}
_FLOW_LOCK: threading.Lock = threading.Lock()


@dataclass(frozen=True)
class GoogleOAuthCompletion:
    account_id: int
    email: str


def _seconds(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _prune_flows() -> None:
    now: float = time.time()
    expired: list[str] = [
        key
        for key, value in _FLOW_STORE.items()
        if now - _seconds(value.get("created_at")) > FLOW_TTL_SECONDS
    ]
    for key in expired:
        del _FLOW_STORE[key]


def _pkce() -> tuple[str, str]:
    verifier: str = secrets.token_urlsafe(64)
    digest: bytes = hashlib.sha256(verifier.encode()).digest()
    challenge: str = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _authorize_params(
    client_id: str,
    redirect_uri: str,
    challenge: str,
    state: str,
    login_hint: str = "",
) -> dict[str, str]:
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": f"openid email {GOOGLE_MAIL_SCOPE}",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if login_hint.strip():
        params["login_hint"] = login_hint.strip()
    return params


def prepare_google_oauth(
    settings: Settings,
    user_id: int,
    account_id: int,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict[str, str]:
    from hx_email.server.mail.imap.impl.proxy import load_group_proxy

    if not client_id.strip() or not redirect_uri.strip():
        raise ValueError("Google OAuth Client ID and redirect URI are required")
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT primary_address, provider FROM email_accounts
            WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id),
        ).fetchone()
    if row is None:
        raise ValueError("Email account not found")
    if str(row["provider"]) != "gmail":
        raise ValueError("Google OAuth is only available for Gmail accounts")

    verifier, challenge = _pkce()
    state: str = secrets.token_urlsafe(32)
    proxy_url: str = load_group_proxy(settings, account_id)
    with _FLOW_LOCK:
        _prune_flows()
        _FLOW_STORE[state] = {
            "created_at": time.time(),
            "user_id": user_id,
            "account_id": account_id,
            "email": str(row["primary_address"]),
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "redirect_uri": redirect_uri.strip(),
            "verifier": verifier,
            "proxy_url": proxy_url,
            "group_id": None,
            "status": FLOW_STATUS_PENDING,
            "result_email": "",
            "error": "",
        }
    params: dict[str, str] = _authorize_params(
        client_id.strip(),
        redirect_uri.strip(),
        challenge,
        state,
        login_hint=str(row["primary_address"]),
    )
    return {"authorization_url": f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}", "state": state}


def prepare_google_oauth_accountless(
    settings: Settings,
    user_id: int,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    group_id: int | None = None,
) -> dict[str, str]:
    """Prepare a Google authorization link without a pre-typed email address.

    The email is discovered from Google's userinfo response during the
    callback, so the user never has to type it in the UI.
    """
    if not client_id.strip() or not redirect_uri.strip():
        raise ValueError("Google OAuth Client ID and redirect URI are required")

    verifier, challenge = _pkce()
    state: str = secrets.token_urlsafe(32)
    with _FLOW_LOCK:
        _prune_flows()
        _FLOW_STORE[state] = {
            "created_at": time.time(),
            "user_id": user_id,
            "account_id": None,
            "email": "",
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "redirect_uri": redirect_uri.strip(),
            "verifier": verifier,
            "proxy_url": "",
            "group_id": group_id,
            "status": FLOW_STATUS_PENDING,
            "result_email": "",
            "error": "",
        }
    params: dict[str, str] = _authorize_params(
        client_id.strip(),
        redirect_uri.strip(),
        challenge,
        state,
    )
    return {"authorization_url": f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}", "state": state}


def google_flow_status(state: str) -> dict[str, object]:
    """Return the current completion status of a flow without consuming it."""
    with _FLOW_LOCK:
        _prune_flows()
        flow = _FLOW_STORE.get(state)
    if flow is None:
        return {
            "status": "missing",
            "email": "",
            "error": "授权流程已过期, 请重新生成授权链接",
        }
    return {
        "status": str(flow.get("status") or FLOW_STATUS_PENDING),
        "email": str(flow.get("result_email") or ""),
        "error": str(flow.get("error") or ""),
    }


def _mark_flow_result(
    state: str,
    status: str,
    email: str = "",
    error: str = "",
) -> None:
    with _FLOW_LOCK:
        flow = _FLOW_STORE.get(state)
        if flow is not None:
            flow["status"] = status
            flow["result_email"] = email
            flow["error"] = error


def complete_google_oauth(
    settings: Settings,
    code: str,
    state: str,
) -> GoogleOAuthCompletion:
    with _FLOW_LOCK:
        _prune_flows()
        flow = _FLOW_STORE.get(state)
    if flow is None:
        raise ValueError("Google OAuth state is missing or expired")
    if str(flow.get("status")) == FLOW_STATUS_DONE:
        raise ValueError("This authorization link has already been completed")

    try:
        tokens = exchange_google_code(
            str(flow["client_id"]),
            str(flow["client_secret"]),
            code,
            str(flow["redirect_uri"]),
            str(flow["verifier"]),
            str(flow["proxy_url"]),
        )
        access_token: str = str(tokens.get("access_token") or "")
        refresh_token: str = str(tokens.get("refresh_token") or "")
        if not access_token or not refresh_token:
            raise RuntimeError("Google did not return offline access; revoke access and try again")
        authorized_email: str = fetch_google_email(access_token, str(flow["proxy_url"])).lower()
        user_id: int = int(str(flow["user_id"]))
        account_id_value: object = flow.get("account_id")
        if account_id_value is not None:
            expected_email: str = str(flow["email"]).strip().lower()
            if authorized_email != expected_email:
                raise RuntimeError(
                    f"Authorized Google account {authorized_email} does not match {expected_email}"
                )
            account_id: int = int(str(account_id_value))
            update_account_credentials(
                settings,
                user_id,
                account_id,
                str(flow["client_id"]),
                refresh_token,
                authorized_email,
            )
        else:
            group_value: object = flow.get("group_id")
            group_id: int | None = int(str(group_value)) if group_value is not None else None
            account_id = save_credentials_by_email(
                settings,
                user_id,
                authorized_email,
                str(flow["client_id"]),
                refresh_token,
                group_id,
            )
        _mark_flow_result(state, FLOW_STATUS_DONE, email=authorized_email)
        return GoogleOAuthCompletion(account_id=account_id, email=authorized_email)
    except (ValueError, RuntimeError) as oauth_error:
        _mark_flow_result(state, FLOW_STATUS_ERROR, error=str(oauth_error))
        raise
