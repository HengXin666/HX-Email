"""Microsoft Graph API helpers — token acquisition and message parsing."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from threading import Lock
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from hx_email.server.mail import MailboxMessage

logger = logging.getLogger(__name__)

# ── Token cache ────────────────────────────────────────────────────────────

_GRAPH_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_GRAPH_TOKEN_LOCK: Lock = Lock()
_GRAPH_TOKEN_URL: str = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH_SCOPE: str = "https://graph.microsoft.com/.default offline_access"
_GRAPH_TENANTS: tuple[str, ...] = ("consumers", "common")

_GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"


def get_graph_token(client_id: str, refresh_token: str, *, tenant: str = "consumers") -> str:
    """Get a Microsoft Graph API access token with caching (60s TTL)."""
    cache_key: str = (
        f"{tenant}:{client_id}:{hashlib.sha256(refresh_token.encode()).hexdigest()[:16]}"
    )
    with _GRAPH_TOKEN_LOCK:
        cached = _GRAPH_TOKEN_CACHE.get(cache_key)
        if cached:
            token, expires = cached
            if time.monotonic() < expires:
                return token

    token_url: str = _GRAPH_TOKEN_URL.format(tenant=tenant)
    body: bytes = urlencode(
        {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": _GRAPH_SCOPE,
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
                raise RuntimeError(
                    f"Graph OAuth token failed (tenant={tenant}): {error} — {desc[:200]}"
                )
            expires_in = int(str(data.get("expires_in", 3599)))
            ttl = max(0, expires_in - 60)
            with _GRAPH_TOKEN_LOCK:
                _GRAPH_TOKEN_CACHE[cache_key] = (access_token, time.monotonic() + ttl)
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
            f"Graph OAuth token expired or invalid (tenant={tenant}): {error} — {desc[:200]}"
        ) from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Graph token network error (tenant={tenant}): {exc}") from exc


def try_get_graph_token(client_id: str, refresh_token: str) -> tuple[str, str]:
    """Try to get a Graph API token, falling through tenants. Returns (token, tenant)."""
    last_error: RuntimeError | None = None
    for tenant in _GRAPH_TENANTS:
        try:
            token: str = get_graph_token(client_id, refresh_token, tenant=tenant)
            return token, tenant
        except RuntimeError as exc:
            last_error = exc
            logger.debug("Graph token failed for tenant=%s: %s", tenant, exc)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to get Graph token: no tenants available")


# ── HTTP helpers ────────────────────────────────────────────────────────────


def graph_get(url: str, access_token: str, *, timeout: int = 30) -> dict[str, Any]:
    """Make an authenticated GET request to Microsoft Graph API."""
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())  # type: ignore[no-any-return]


# ── Message parsing ─────────────────────────────────────────────────────────


def parse_graph_message(data: dict[str, Any], account_email: str) -> MailboxMessage:
    """Parse a Graph API message resource into a MailboxMessage."""
    subject: str = str(data.get("subject") or "")

    from_address: str = ""
    from_obj = data.get("from")
    if isinstance(from_obj, dict):
        email_addr_obj = from_obj.get("emailAddress")
        if isinstance(email_addr_obj, dict):
            name = str(email_addr_obj.get("name") or "")
            addr = str(email_addr_obj.get("address") or "")
            from_address = f"{name} <{addr}>" if name else addr

    recipient_address: str | None = None
    to_recipients = data.get("toRecipients")
    if isinstance(to_recipients, list) and to_recipients:
        first_to = to_recipients[0]
        if isinstance(first_to, dict):
            email_addr_obj = first_to.get("emailAddress")
            if isinstance(email_addr_obj, dict):
                recipient_address = str(email_addr_obj.get("address") or "") or None

    received_at: str = str(data.get("receivedDateTime") or "")

    body_text: str = ""
    body_obj = data.get("body")
    if isinstance(body_obj, dict):
        body_text = str(body_obj.get("content") or "")

    return MailboxMessage(
        recipient_address=recipient_address,
        subject=subject,
        body=body_text,
        from_address=from_address,
        received_at=received_at,
        message_id=str(data.get("id") or ""),
    )


def graph_message_id(data: dict[str, Any]) -> str:
    """Extract the message ID from a Graph API message resource."""
    return str(data.get("id") or "")
