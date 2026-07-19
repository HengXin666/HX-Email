"""Microsoft Graph API helpers — token acquisition and message parsing."""

from __future__ import annotations

import hashlib
import logging
import time
from threading import Lock
from typing import Any

import requests

from hx_email.config import MICROSOFT_MAIL_SCOPE
from hx_email.server.mail import MailboxMessage

logger = logging.getLogger(__name__)

# ── Token cache ────────────────────────────────────────────────────────────

_GRAPH_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_GRAPH_TOKEN_LOCK: Lock = Lock()
_GRAPH_TOKEN_URL: str = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH_SCOPE: str = MICROSOFT_MAIL_SCOPE
_GRAPH_TENANTS: tuple[str, ...] = ("consumers", "common")

_GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"


def build_proxies(proxy_url: str = "") -> dict[str, str] | None:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def get_graph_token(
    client_id: str,
    refresh_token: str,
    *,
    tenant: str = "consumers",
    proxy_url: str = "",
) -> tuple[str, str]:
    """Get a Microsoft Graph API access token with caching (60s TTL)."""
    token_hash: str = hashlib.sha256(refresh_token.encode()).hexdigest()[:16]
    cache_key: str = f"{tenant}:{proxy_url}:{client_id}:{token_hash}"
    with _GRAPH_TOKEN_LOCK:
        cached = _GRAPH_TOKEN_CACHE.get(cache_key)
        if cached:
            token, expires = cached
            if time.monotonic() < expires:
                return token, ""

    try:
        response = requests.post(
            _GRAPH_TOKEN_URL.format(tenant=tenant),
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": _GRAPH_SCOPE,
            },
            timeout=15,
            proxies=build_proxies(proxy_url),
        )
        if response.status_code != 200:
            raise RuntimeError(
                "Graph OAuth token failed "
                f"(tenant={tenant}, status={response.status_code}): {response.text[:200]}"
            )
        data: dict[str, object] = response.json()
        access_token = str(data.get("access_token", ""))
        if not access_token:
            error = str(data.get("error", "unknown"))
            desc = str(data.get("error_description", str(data)))
            raise RuntimeError(
                f"Graph OAuth token failed (tenant={tenant}): {error} — {desc[:200]}"
            )
        expires_in = int(str(data.get("expires_in", 3599)))
        ttl = max(0, expires_in - 60)
        rotated_token: str = str(data.get("refresh_token") or "")
        with _GRAPH_TOKEN_LOCK:
            _GRAPH_TOKEN_CACHE[cache_key] = (access_token, time.monotonic() + ttl)
            if rotated_token:
                rotated_hash: str = hashlib.sha256(rotated_token.encode()).hexdigest()[:16]
                rotated_key: str = f"{tenant}:{proxy_url}:{client_id}:{rotated_hash}"
                _GRAPH_TOKEN_CACHE[rotated_key] = (access_token, time.monotonic() + ttl)
        return access_token, rotated_token
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Graph token network error (tenant={tenant}): {exc}") from exc


def try_get_graph_token(
    client_id: str, refresh_token: str, proxy_url: str = ""
) -> tuple[str, str, str]:
    """Try to get a Graph API token, falling through tenants. Returns (token, tenant)."""
    last_error: RuntimeError | None = None
    for tenant in _GRAPH_TENANTS:
        try:
            token, rotated_token = get_graph_token(
                client_id, refresh_token, tenant=tenant, proxy_url=proxy_url
            )
            return token, tenant, rotated_token
        except RuntimeError as exc:
            last_error = exc
            logger.debug("Graph token failed for tenant=%s: %s", tenant, exc)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to get Graph token: no tenants available")


# ── HTTP helpers ────────────────────────────────────────────────────────────


def graph_get(
    url: str,
    access_token: str,
    *,
    timeout: int = 30,
    proxy_url: str = "",
) -> dict[str, Any]:
    """Make an authenticated GET request to Microsoft Graph API."""
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=timeout,
        proxies=build_proxies(proxy_url),
    )
    if response.status_code != 200:
        raise RuntimeError(f"Graph GET failed status={response.status_code}: {response.text[:200]}")
    data: dict[str, Any] = response.json()
    return data


def graph_send_mail(
    access_token: str,
    *,
    recipient: str,
    subject: str,
    body: str,
    proxy_url: str = "",
) -> None:
    """Send a plain-text email through Microsoft Graph /me/sendMail."""
    url: str = f"{_GRAPH_BASE_URL}/me/sendMail"
    payload: dict[str, object] = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": recipient}}],
        },
        "saveToSentItems": True,
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
        proxies=build_proxies(proxy_url),
    )
    if response.status_code != 202:
        raise RuntimeError(
            f"Graph sendMail failed status={response.status_code}: {response.text[:200]}"
        )


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
