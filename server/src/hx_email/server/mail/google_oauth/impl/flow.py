"""Short-lived Google OAuth PKCE flow bound to one local account."""

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
from hx_email.security import encrypt_secret
from hx_email.server.mail.google_oauth.impl.tokens import (
    GOOGLE_MAIL_SCOPE,
    exchange_google_code,
    fetch_google_email,
)

GOOGLE_AUTHORIZE_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
FLOW_TTL_SECONDS: int = 20 * 60

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
        }
    params: dict[str, str] = {
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri.strip(),
        "response_type": "code",
        "scope": f"openid email {GOOGLE_MAIL_SCOPE}",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return {"authorization_url": f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}", "state": state}


def complete_google_oauth(
    settings: Settings,
    code: str,
    state: str,
) -> GoogleOAuthCompletion:
    with _FLOW_LOCK:
        _prune_flows()
        flow = _FLOW_STORE.pop(state, None)
    if flow is None:
        raise ValueError("Google OAuth state is missing or expired")

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
    expected_email: str = str(flow["email"]).strip().lower()
    if authorized_email != expected_email:
        raise RuntimeError(
            f"Authorized Google account {authorized_email} does not match {expected_email}"
        )
    account_id: int = int(str(flow["account_id"]))
    user_id: int = int(str(flow["user_id"]))
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            UPDATE email_accounts
            SET client_id = ?, refresh_token = ?, imap_password = '', username = ?,
                provider = 'gmail'
            WHERE id = ? AND user_id = ?
            """,
            (
                str(flow["client_id"]),
                encrypt_secret(settings, refresh_token),
                authorized_email,
                account_id,
                user_id,
            ),
        )
    if cursor.rowcount != 1:
        raise RuntimeError("Email account no longer exists")
    return GoogleOAuthCompletion(account_id=account_id, email=authorized_email)
