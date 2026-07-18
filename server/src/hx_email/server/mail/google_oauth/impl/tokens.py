"""Google OAuth HTTP exchanges and access-token cache."""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

import requests

from hx_email.config import Settings
from hx_email.server.settings_service import get_setting

GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL: str = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_MAIL_SCOPE: str = "https://mail.google.com/"

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_LOCK: threading.Lock = threading.Lock()


def _proxies(proxy_url: str) -> dict[str, str] | None:
    value: str = proxy_url.strip()
    if not value:
        return None
    normalized: str = value if "://" in value else f"http://{value}"
    return {"http": normalized, "https": normalized}


def _token_payload(
    client_id: str,
    client_secret: str,
    grant_type: str,
    **values: str,
) -> dict[str, str]:
    payload: dict[str, str] = {
        "client_id": client_id,
        "grant_type": grant_type,
        **values,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    return payload


def exchange_google_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    proxy_url: str = "",
) -> dict[str, object]:
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data=_token_payload(
            client_id,
            client_secret,
            "authorization_code",
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        ),
        timeout=20,
        proxies=_proxies(proxy_url),
    )
    if response.status_code != 200:
        raise RuntimeError(f"Google OAuth code exchange failed: {response.text[:300]}")
    return dict(response.json())


def fetch_google_email(access_token: str, proxy_url: str = "") -> str:
    response = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
        proxies=_proxies(proxy_url),
    )
    if response.status_code != 200:
        raise RuntimeError(f"Google user info failed: {response.text[:300]}")
    data: dict[str, Any] = response.json()
    email: str = str(data.get("email") or "").strip()
    if not email:
        raise RuntimeError("Google authorization did not return an email address")
    return email


def get_google_access_token(
    settings: Settings,
    client_id: str,
    refresh_token: str,
    proxy_url: str = "",
) -> str:
    token_hash: str = hashlib.sha256(refresh_token.encode()).hexdigest()[:16]
    cache_key: str = f"{client_id}:{token_hash}:{proxy_url}"
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if cached is not None and time.monotonic() < cached[1]:
            return cached[0]

    client_secret: str = get_setting(settings, "google_oauth_client_secret", "")
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data=_token_payload(
            client_id,
            client_secret,
            "refresh_token",
            refresh_token=refresh_token,
        ),
        timeout=20,
        proxies=_proxies(proxy_url),
    )
    if response.status_code != 200:
        raise RuntimeError(f"Google OAuth refresh failed: {response.text[:300]}")
    data: dict[str, Any] = response.json()
    access_token: str = str(data.get("access_token") or "")
    if not access_token:
        raise RuntimeError("Google OAuth refresh returned no access token")
    expires_in: int = int(data.get("expires_in") or 3600)
    with _TOKEN_LOCK:
        _TOKEN_CACHE[cache_key] = (access_token, time.monotonic() + max(0, expires_in - 60))
    return access_token


def refresh_google_token(
    settings: Settings,
    client_id: str,
    refresh_token: str,
    proxy_url: str = "",
) -> dict[str, object]:
    try:
        get_google_access_token(settings, client_id, refresh_token, proxy_url)
        return {
            "success": True,
            "message": "Google token refreshed successfully",
            "error_detail": "",
        }
    except RuntimeError as error:
        return {
            "success": False,
            "message": "Google token refresh failed",
            "error_detail": str(error),
        }
