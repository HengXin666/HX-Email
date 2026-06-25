"""IMAP helper functions and OAuth token utilities — extracted from imap_provider."""

from __future__ import annotations

import email
import hashlib
import json
import logging
import time
from email.header import decode_header
from email.utils import parsedate_to_datetime
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ── OAuth token cache ────────────────────────────────────────────────────

_IMAP_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_IMAP_TOKEN_LOCK: Lock = Lock()
_IMAP_TOKEN_URL_TEMPLATE: str = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_IMAP_SCOPE: str = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
_IMAP_TENANTS: tuple[str, ...] = ("consumers", "common")
_OUTLOOK_PROVIDERS: frozenset[str] = frozenset({"outlook", "hotmail"})
_OUTLOOK_IMAP_SERVERS: tuple[str, ...] = ("outlook.live.com", "outlook.office365.com")

# ── MIME helpers ─────────────────────────────────────────────────────────


def decode_mime_header(value: str) -> str:
    parts: list[str] = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            try:
                parts.append(text.decode(charset or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                parts.append(text.decode("utf-8", errors="replace"))
        else:
            parts.append(str(text))
    return "".join(parts)


def parse_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(str(date_str))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(date_str)[:19]


def get_body(msg: email.message.Message) -> str:
    """Extract the best available text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except (LookupError, TypeError):
                        return payload.decode("utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except (LookupError, TypeError):
                        return payload.decode("utf-8", errors="replace")
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        charset = msg.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except (LookupError, TypeError):
            return payload.decode("utf-8", errors="replace")
    return str(msg.get_payload())


def recipient_from_envelope(msg: email.message.Message, account_email: str) -> str | None:
    """Try to determine which of our addresses this message was sent to."""
    for hdr in ("delivered-to", "x-original-to", "x-delivered-to"):
        val = msg.get(hdr)
        if val:
            addr = str(val).strip().lower()
            if "@" in addr:
                return addr
    to_val = msg.get("to")
    if to_val:
        return str(to_val).strip().lower()
    return account_email.lower()


def extract_from(msg: email.message.Message) -> str:
    from_val = msg.get("from") or ""
    return decode_mime_header(str(from_val))


# ── OAuth token helpers ──────────────────────────────────────────────────


def get_imap_token(client_id: str, refresh_token: str, *, tenant: str = "consumers") -> str:
    """Get an IMAP-specific access token with caching (60s TTL)."""
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
                raise RuntimeError(f"OAuth 令牌无效 (tenant={tenant}): {error} — {desc[:200]}")
            expires_in = int(str(data.get("expires_in", 3599)))
            ttl = max(0, expires_in - 60)
            with _IMAP_TOKEN_LOCK:
                _IMAP_TOKEN_CACHE[cache_key] = (access_token, time.monotonic() + ttl)
            return access_token
    except HTTPError as exc:
        try:
            err_data: dict[str, object] = json.loads(exc.read().decode())
            error = str(err_data.get("error", "unknown"))
            desc = str(err_data.get("error_description", str(exc)))
        except Exception:
            error = str(exc.code)
            desc = str(exc)
        raise RuntimeError(
            f"OAuth 令牌已过期或无效 (tenant={tenant}): {error} — {desc[:200]}"
        ) from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"获取 IMAP 令牌网络错误 (tenant={tenant}): {exc}") from exc


def try_get_imap_token(client_id: str, refresh_token: str) -> tuple[str, str]:
    """Try to get an IMAP token, falling through tenants."""
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
    raise RuntimeError("Failed to get IMAP token: no tenants available")  # pragma: no cover
