from __future__ import annotations

import hashlib
import json
import logging
import time
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_IMAP_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_IMAP_TOKEN_LOCK: Lock = Lock()
_IMAP_TOKEN_URL_TEMPLATE: str = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_IMAP_SCOPE: str = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
_IMAP_TENANTS: tuple[str, ...] = ("consumers", "common")


def get_imap_token(client_id: str, refresh_token: str, *, tenant: str = "consumers") -> str:
    cache_key: str = (
        f"{tenant}:{client_id}:{hashlib.sha256(refresh_token.encode()).hexdigest()[:16]}"
    )
    with _IMAP_TOKEN_LOCK:
        cached = _IMAP_TOKEN_CACHE.get(cache_key)
        if cached:
            token, expires = cached
            if time.monotonic() < expires:
                return token
    token_url: str = _IMAP_TOKEN_URL_TEMPLATE.format(tenant=tenant)
    body: bytes = urlencode(
        {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": _IMAP_SCOPE,
        }
    ).encode()
    try:
        req = Request(
            token_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(req, timeout=15) as resp:
            data: dict[str, object] = json.loads(resp.read().decode())
            access_token = str(data.get("access_token", ""))
            if not access_token:
                error = str(data.get("error", "unknown"))
                desc = str(data.get("error_description", str(data)))
                raise RuntimeError(f"OAuth 令牌无效 (tenant={tenant}): {error} - {desc[:200]}")
            expires_in = int(str(data.get("expires_in", 3599)))
            ttl = max(0, expires_in - 60)
            with _IMAP_TOKEN_LOCK:
                _IMAP_TOKEN_CACHE[cache_key] = (access_token, time.monotonic() + ttl)
            return access_token
    except HTTPError as exc:
        error, desc = read_http_error(exc)
        raise RuntimeError(
            f"OAuth 令牌已过期或无效 (tenant={tenant}): {error} - {desc[:200]}"
        ) from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"获取 IMAP 令牌网络错误 (tenant={tenant}): {exc}") from exc


def try_get_imap_token(client_id: str, refresh_token: str) -> tuple[str, str]:
    last_error: RuntimeError | None = None
    for tenant in _IMAP_TENANTS:
        try:
            token: str = get_imap_token(client_id, refresh_token, tenant=tenant)
            return token, tenant
        except RuntimeError as exc:
            last_error = exc
            logger.debug("IMAP token failed for tenant=%s: %s", tenant, exc)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to get IMAP token: no tenants available")


def read_http_error(exc: HTTPError) -> tuple[str, str]:
    try:
        err_data: dict[str, object] = json.loads(exc.read().decode())
        return str(err_data.get("error", "unknown")), str(err_data.get("error_description", exc))
    except Exception:
        return str(exc.code), str(exc)
