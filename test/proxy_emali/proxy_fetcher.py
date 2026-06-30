"""Graph proxy fetcher mirroring ref/outlookEmailPlus requests proxy flow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

_TOKEN_URL: str = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE: str = "https://graph.microsoft.com/.default"
_TIMEOUT_SECONDS: int = 30


@dataclass(frozen=True)
class EmailItem:
    id: str
    subject: str
    from_address: str
    date: str
    is_read: bool
    has_attachments: bool
    body_preview: str


@dataclass(frozen=True)
class FetchResult:
    success: bool
    method: str
    emails: list[EmailItem]
    error: str = ""


def fetch_emails(
    email_addr: str,
    client_id: str,
    refresh_token: str,
    proxy_url: str,
    folder: str = "inbox",
    top: int = 20,
    skip: int = 0,
) -> FetchResult:
    _ = email_addr
    proxies = build_proxies(proxy_url)
    try:
        logger.info("request token through proxy=%s", proxy_url)
        token = request_graph_token(client_id, refresh_token, proxies)
        logger.info("request graph messages through proxy=%s", proxy_url)
        emails = request_graph_messages(token, proxies, folder=folder, top=top, skip=skip)
        return FetchResult(
            success=True,
            method=f"Graph API via requests proxy {proxy_url}",
            emails=emails,
        )
    except Exception as exc:
        error = str(exc) or type(exc).__name__
        logger.exception("proxy graph fetch failed: %s", error)
        return FetchResult(False, f"Graph API via requests proxy {proxy_url}", [], error)


def build_proxies(proxy_url: str) -> dict[str, str] | None:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def request_graph_token(
    client_id: str,
    refresh_token: str,
    proxies: dict[str, str] | None,
) -> str:
    response = requests.post(
        _TOKEN_URL,
        data={
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": _GRAPH_SCOPE,
        },
        timeout=_TIMEOUT_SECONDS,
        proxies=proxies,
    )
    if response.status_code != 200:
        raise RuntimeError(f"token failed status={response.status_code} body={response.text[:500]}")
    payload: dict[str, Any] = response.json()
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError(f"token missing body={str(payload)[:500]}")
    return token


def request_graph_messages(
    access_token: str,
    proxies: dict[str, str] | None,
    *,
    folder: str,
    top: int,
    skip: int,
) -> list[EmailItem]:
    folder_name = resolve_graph_folder(folder)
    response = requests.get(
        f"{_GRAPH_BASE_URL}/me/mailFolders/{folder_name}/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Prefer": "outlook.body-content-type='text'",
        },
        params={
            "$top": max(1, min(top, 50)),
            "$skip": max(0, skip),
            "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,bodyPreview",
            "$orderby": "receivedDateTime desc",
        },
        timeout=_TIMEOUT_SECONDS,
        proxies=proxies,
    )
    if response.status_code != 200:
        raise RuntimeError(f"graph failed status={response.status_code} body={response.text[:500]}")
    payload: dict[str, Any] = response.json()
    items = payload.get("value")
    if not isinstance(items, list):
        return []
    return [parse_email(item) for item in items if isinstance(item, dict)]


def resolve_graph_folder(folder: str) -> str:
    mapping: dict[str, str] = {
        "inbox": "inbox",
        "junk": "junkemail",
        "junkemail": "junkemail",
        "junk email": "junkemail",
        "spam": "junkemail",
        "deleted": "deleteditems",
        "deleteditems": "deleteditems",
        "deleted items": "deleteditems",
        "trash": "deleteditems",
    }
    return mapping.get((folder or "inbox").strip().lower(), "inbox")


def parse_email(item: dict[str, Any]) -> EmailItem:
    from_address = ""
    from_obj = item.get("from")
    if isinstance(from_obj, dict):
        email_obj = from_obj.get("emailAddress")
        if isinstance(email_obj, dict):
            name = str(email_obj.get("name") or "")
            address = str(email_obj.get("address") or "")
            from_address = f"{name} <{address}>" if name else address
    return EmailItem(
        id=str(item.get("id") or ""),
        subject=str(item.get("subject") or "No Subject"),
        from_address=from_address,
        date=str(item.get("receivedDateTime") or ""),
        is_read=bool(item.get("isRead", False)),
        has_attachments=bool(item.get("hasAttachments", False)),
        body_preview=str(item.get("bodyPreview") or ""),
    )
