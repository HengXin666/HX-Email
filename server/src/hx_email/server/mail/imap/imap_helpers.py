"""IMAP helper functions and OAuth token utilities — extracted from imap_provider."""

from __future__ import annotations

import email
import hashlib
import imaplib
import json
import logging
import time
from email.header import decode_header
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from hx_email.config import Settings

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


# ── Proxy helpers ──────────────────────────────────────────────────────────


def load_group_proxy(settings: Settings, account_id: int) -> str:
    """Look up proxy_url from the group linked to this account.

    Checks usable_emails (any kind) first, then falls back to email_accounts.group_id.
    """
    import logging

    from hx_email.database import connect as _connect

    _log = logging.getLogger(__name__)

    with _connect(settings) as conn:
        row = conn.execute(
            """
            SELECT g.proxy_url FROM groups g
            JOIN usable_emails ue ON ue.group_id = g.id
            WHERE ue.email_account_id = ?
              AND g.proxy_url IS NOT NULL AND g.proxy_url != ''
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        if row:
            result: str = str(row["proxy_url"]).strip()
            _log.info(
                "load_group_proxy(account=%d): found via usable_emails -> %s", account_id, result
            )
            return result
        # Fallback: check email_accounts.group_id directly
        row = conn.execute(
            """
            SELECT g.proxy_url FROM groups g
            JOIN email_accounts ea ON ea.group_id = g.id
            WHERE ea.id = ?
              AND g.proxy_url IS NOT NULL AND g.proxy_url != ''
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        if row:
            result = str(row["proxy_url"]).strip()
            _log.info(
                "load_group_proxy(account=%d): found via email_accounts.group_id -> %s",
                account_id,
                result,
            )
            return result
    _log.warning("load_group_proxy(account=%d): no proxy found", account_id)
    return ""


def imap_connect_via_proxy(
    proxy_url: str, host: str, port: int, timeout: int = 30
) -> imaplib.IMAP4:
    """Create an IMAP4 connection through an HTTP CONNECT proxy tunnel."""
    import socket
    import ssl as _ssl

    proxy = proxy_url
    if "://" in proxy:
        proxy = proxy.split("://", 1)[1]
    if ":" in proxy:
        proxy_host, proxy_port_str = proxy.rsplit(":", 1)
        proxy_port_num = int(proxy_port_str)
    else:
        proxy_host = proxy
        proxy_port_num = 8080
    sock = socket.create_connection((proxy_host, proxy_port_num), timeout=timeout)
    connect_cmd = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n"
    sock.sendall(connect_cmd.encode())
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response += chunk
    status_line = response.split(b"\r\n")[0].decode(errors="replace")
    if "200" not in status_line:
        sock.close()
        raise RuntimeError(f"代理 CONNECT 失败: {status_line}")
    ctx = _ssl.create_default_context()
    ssl_sock = ctx.wrap_socket(sock, server_hostname=host)
    # Use __new__ to create IMAP4 without triggering its open() which
    # would try to connect to localhost:143 (Python 3.13+ behavior).
    conn = imaplib.IMAP4.__new__(imaplib.IMAP4)
    conn.debug = 0
    conn.state = "LOGOUT"
    conn.literal = None
    conn.tagged_commands = {}
    conn.untagged_responses = {}
    conn.continuation_response = ""
    conn.is_readonly = False
    conn.tagnum = 0
    conn._tls_established = False  # type: ignore[attr-defined]
    conn._mode_ascii()
    conn.host = host
    conn.port = port
    conn.sock = ssl_sock
    conn.file = ssl_sock.makefile("rb")
    conn._connect()
    return conn
