"""Minimal email fetcher — mirrors reference api_get_emails flow.

Graph API (refresh_token → access_token → MS Graph) → IMAP fallback.
Self-contained: no database, no Flask — just urllib + imaplib.
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import json
import logging
import ssl
import time
from dataclasses import dataclass, field
from email.header import decode_header
from threading import Lock
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"
_TOKEN_URL: str = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH_SCOPE: str = "https://graph.microsoft.com/.default offline_access"
_IMAP_SCOPE: str = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
_TENANTS: tuple[str, ...] = ("consumers", "common")

_IMAP_SERVER_NEW: str = "outlook.live.com"
_IMAP_SERVER_OLD: str = "outlook.office365.com"

# ── Token cache ──────────────────────────────────────────────────────────────

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_LOCK: Lock = Lock()


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class EmailItem:
    """A single formatted email, mirroring the reference response format."""

    id: str = ""
    subject: str = ""
    from_address: str = ""
    date: str = ""
    is_read: bool = False
    has_attachments: bool = False
    body_preview: str = ""


@dataclass
class FetchResult:
    """Result of an email fetch operation."""

    success: bool
    emails: list[EmailItem] = field(default_factory=list)
    method: str = ""
    has_more: bool = False
    error: str = ""


# ── OAuth2 token acquisition ─────────────────────────────────────────────────


def _get_oauth_token(
    client_id: str,
    refresh_token: str,
    scope: str,
    *,
    cache_prefix: str = "graph",
) -> str:
    """Exchange a refresh_token for an access_token (with 60s TTL cache)."""
    cache_key: str = (
        f"{cache_prefix}:{client_id}:{hashlib.sha256(refresh_token.encode()).hexdigest()[:16]}"
    )
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if cached:
            token, expires = cached
            if time.monotonic() < expires:
                return token

    last_error: Exception | None = None
    for tenant in _TENANTS:
        token_url: str = _TOKEN_URL.format(tenant=tenant)
        body: bytes = urlencode(
            {
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": scope,
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
                data: dict[str, Any] = json.loads(resp.read().decode())
                access_token: str = str(data.get("access_token", ""))
                if not access_token:
                    err = str(data.get("error", "unknown"))
                    desc = str(data.get("error_description", str(data)))
                    raise RuntimeError(
                        f"OAuth token failed (tenant={tenant}): {err} — {desc[:200]}"
                    )
                expires_in: int = int(str(data.get("expires_in", 3599)))
                ttl: int = max(0, expires_in - 60)
                with _TOKEN_LOCK:
                    _TOKEN_CACHE[cache_key] = (access_token, time.monotonic() + ttl)
                return access_token
        except HTTPError as exc:
            try:
                err_data: dict[str, Any] = json.loads(exc.read().decode())
                err = str(err_data.get("error", "unknown"))
                desc = str(err_data.get("error_description", str(exc)))
            except Exception:
                err = str(exc.code)
                desc = str(exc)
            last_error = RuntimeError(
                f"OAuth token expired/invalid (tenant={tenant}): {err} — {desc[:200]}"
            )
        except RuntimeError:
            raise
        except Exception as exc:
            last_error = RuntimeError(f"Token network error (tenant={tenant}): {exc}")

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to get OAuth token: no tenants available")


def get_graph_token(client_id: str, refresh_token: str) -> str:
    """Get a Microsoft Graph API access token."""
    return _get_oauth_token(client_id, refresh_token, _GRAPH_SCOPE, cache_prefix="graph")


def get_imap_token(client_id: str, refresh_token: str) -> str:
    """Get an IMAP XOAUTH2 access token."""
    return _get_oauth_token(client_id, refresh_token, _IMAP_SCOPE, cache_prefix="imap")


# ── Graph API email fetch ────────────────────────────────────────────────────


def _resolve_graph_folder(folder: str) -> str:
    """Map human-readable folder names to Graph API well-known folder names."""
    mapping: dict[str, str] = {
        "inbox": "inbox",
        "sent": "sentitems",
        "sent items": "sentitems",
        "drafts": "drafts",
        "deleted": "deleteditems",
        "deleted items": "deleteditems",
        "trash": "deleteditems",
        "junk": "junkemail",
        "junk email": "junkemail",
        "spam": "junkemail",
        "archive": "archive",
    }
    return mapping.get(folder.lower().strip(), folder.lower().strip())


def _graph_get(url: str, access_token: str, *, timeout: int = 30) -> dict[str, Any]:
    """Authenticated GET request to Microsoft Graph API."""
    req = Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())  # type: ignore[no-any-return]


def _parse_graph_email(item: dict[str, Any]) -> EmailItem:
    """Parse a single Graph API message resource into an EmailItem."""
    # From
    from_addr: str = ""
    from_obj = item.get("from")
    if isinstance(from_obj, dict):
        ea = from_obj.get("emailAddress")
        if isinstance(ea, dict):
            name: str = str(ea.get("name") or "")
            addr: str = str(ea.get("address") or "")
            from_addr = f"{name} <{addr}>" if name else addr

    # Body preview — use bodyPreview field (plain text), fall back to body content
    preview: str = str(item.get("bodyPreview") or "")
    if not preview:
        body_obj = item.get("body")
        if isinstance(body_obj, dict):
            body_text: str = str(body_obj.get("content") or "")
            preview = body_text[:200]
            if len(body_text) > 200:
                preview = preview + "..."

    return EmailItem(
        id=str(item.get("id") or ""),
        subject=str(item.get("subject") or "No Subject"),
        from_address=from_addr,
        date=str(item.get("receivedDateTime") or ""),
        is_read=bool(item.get("isRead", False)),
        has_attachments=bool(item.get("hasAttachments", False)),
        body_preview=preview,
    )


def fetch_emails_graph(
    access_token: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
) -> tuple[list[EmailItem], bool]:
    """Fetch emails via Microsoft Graph API.

    Returns (emails, has_more).
    """
    folder_path: str = _resolve_graph_folder(folder)
    query: str = urlencode(
        {
            "$top": str(top),
            "$skip": str(skip),
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,isRead,hasAttachments,bodyPreview,body",
        },
        quote_via=quote,
    )
    url: str = f"{_GRAPH_BASE_URL}/me/mailFolders/{folder_path}/messages?{query}"
    data: dict[str, Any] = _graph_get(url, access_token)
    items = data.get("value")
    emails: list[EmailItem] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                emails.append(_parse_graph_email(item))
    has_more: bool = len(emails) >= top
    return emails, has_more


# ── IMAP email fetch (XOAUTH2 fallback) ──────────────────────────────────────


def _decode_mime_header(value: str) -> str:
    """Decode RFC 2047 encoded header value."""
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


def fetch_emails_imap(
    email_addr: str,
    credential: str,
    imap_server: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
    *,
    use_password: bool = False,
) -> tuple[list[EmailItem], bool]:
    """Fetch emails via IMAP (XOAUTH2 or password auth).

    Args:
        credential: access_token (for XOAUTH2) or password (for login).
        use_password: if True, use password-based LOGIN instead of XOAUTH2.

    Returns (emails, has_more).
    """
    conn: imaplib.IMAP4_SSL | None = None
    try:
        ctx: ssl.SSLContext = ssl.create_default_context()
        conn = imaplib.IMAP4_SSL(imap_server, 993, ssl_context=ctx, timeout=30)

        # IMAP ID command (some servers require it)
        try:
            imaplib.Commands["ID"] = ("NONAUTH", "AUTH", "SELECTED")
            conn._simple_command("ID", '("name" "hxemail" "version" "1.0")')
        except Exception:
            pass

        if use_password:
            conn.login(email_addr, credential)
            logger.info("IMAP password login OK for %s on %s", email_addr, imap_server)
        else:
            # XOAUTH2
            auth_string: bytes = f"user={email_addr}\x01auth=Bearer {credential}\x01\x01".encode()
            conn.authenticate("XOAUTH2", lambda _: auth_string)
            logger.info("IMAP XOAUTH2 authenticated for %s on %s", email_addr, imap_server)

        # Resolve folder (try common folder names)
        folder_candidates: list[str] = [folder, f'"{folder}"']
        selected: str | None = None
        for name in folder_candidates:
            try:
                status, _data = conn.select(name, readonly=True)
                if status == "OK":
                    selected = name
                    break
            except Exception:
                continue
        if not selected:
            raise RuntimeError(f"IMAP folder not found: {folder}")

        # SEARCH all → paginate
        status, data = conn.uid("SEARCH", None, "ALL")  # type: ignore[arg-type]
        if status != "OK":
            raise RuntimeError(f"IMAP SEARCH failed: {status}")
        uid_bytes: bytes = data[0] if data and data[0] else b""
        if not uid_bytes:
            return [], False
        uids: list[bytes] = uid_bytes.split()
        total: int = len(uids)
        start_idx: int = max(0, total - skip - top)
        end_idx: int = total - skip
        if start_idx >= end_idx:
            return [], False
        paged_uids: list[bytes] = uids[start_idx:end_idx][::-1]
        logger.info(
            "IMAP %s: %d total, fetching %d (skip=%d top=%d)",
            imap_server,
            total,
            len(paged_uids),
            skip,
            top,
        )

        emails: list[EmailItem] = []
        for uid in paged_uids:
            try:
                f_status, f_data = conn.uid("FETCH", uid, "(FLAGS RFC822)")  # type: ignore[arg-type]
                if f_status != "OK" or not f_data:
                    continue
                raw_bytes: bytes | None = None
                flags_text: str = ""
                for item in f_data:
                    if isinstance(item, tuple) and len(item) >= 2:
                        # Extract flags from first element
                        meta = item[0]
                        if isinstance(meta, bytes | bytearray):
                            flags_text = meta.decode("utf-8", errors="ignore")
                        elif isinstance(meta, str):
                            flags_text = meta
                        raw_bytes = item[1]
                        break
                if not raw_bytes:
                    continue
                msg = email.message_from_bytes(raw_bytes)
                uid_str: str = uid.decode("ascii") if isinstance(uid, bytes) else str(uid)
                body_text: str = _extract_body(msg)
                preview: str = body_text[:200]
                if len(body_text) > 200:
                    preview = preview + "..."
                emails.append(
                    EmailItem(
                        id=uid_str,
                        subject=_decode_mime_header(str(msg.get("subject") or "No Subject")),
                        from_address=_decode_mime_header(str(msg.get("from") or "")),
                        date=str(msg.get("date") or ""),
                        is_read="\\Seen" in flags_text,
                        has_attachments=_has_attachment(msg),
                        body_preview=preview,
                    )
                )
            except Exception:
                continue

        has_more: bool = (skip + top) < total
        return emails, has_more

    except Exception as exc:
        raise RuntimeError(f"IMAP fetch failed ({imap_server}): {exc}") from exc
    finally:
        if conn is not None:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass


def _extract_body(msg: email.message.Message) -> str:
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


def _has_attachment(msg: email.message.Message) -> bool:
    """Detect attachments via Content-Disposition header."""
    if not msg.is_multipart():
        return False
    for part in msg.walk():
        try:
            disp: str = str(part.get("Content-Disposition", "") or "").lower()
        except Exception:
            disp = ""
        if "attachment" in disp:
            return True
    return False


# ── Main orchestrator (mirrors api_get_emails) ───────────────────────────────


def fetch_emails(
    email_addr: str,
    client_id: str,
    refresh_token: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
    *,
    use_imap: bool = False,
    imap_password: str = "",
) -> FetchResult:
    """Fetch emails for an Outlook/Hotmail account.

    Mirrors the reference api_get_emails flow:
      1. Try Graph API (primary)
      2. Fall back to IMAP XOAUTH2 (outlook.live.com)
      3. Fall back to IMAP XOAUTH2 (outlook.office365.com)
      4. Fall back to IMAP password login (both servers)

    Set use_imap=True to skip Graph API and go directly to IMAP.
    Set imap_password for password-based IMAP fallback.
    """
    _t0: float = time.monotonic()

    if not use_imap:
        # ── Step 1: Graph API ──
        try:
            access_token: str = get_graph_token(client_id, refresh_token)
            emails, has_more = fetch_emails_graph(access_token, folder=folder, skip=skip, top=top)
            elapsed_ms: float = (time.monotonic() - _t0) * 1000
            logger.info(
                "Graph API: %d emails, has_more=%s, %dms",
                len(emails),
                has_more,
                elapsed_ms,
            )
            return FetchResult(
                success=True,
                emails=emails,
                method="Graph API",
                has_more=has_more,
            )
        except Exception as exc:
            logger.warning("Graph API failed: %s", exc)

    # ── Step 2: IMAP (outlook.live.com) ──
    try:
        imap_token: str = get_imap_token(client_id, refresh_token)
        emails, has_more = fetch_emails_imap(
            email_addr,
            imap_token,
            _IMAP_SERVER_NEW,
            folder=folder,
            skip=skip,
            top=top,
        )
        elapsed_ms = (time.monotonic() - _t0) * 1000
        logger.info(
            "IMAP (new): %d emails, %dms",
            len(emails),
            elapsed_ms,
        )
        return FetchResult(
            success=True,
            emails=emails,
            method=f"IMAP ({_IMAP_SERVER_NEW})",
            has_more=has_more,
        )
    except Exception as exc:
        logger.warning("IMAP (new) failed: %s", exc)

    # ── Step 3: IMAP (outlook.office365.com) ──
    try:
        imap_token = get_imap_token(client_id, refresh_token)
        emails, has_more = fetch_emails_imap(
            email_addr,
            imap_token,
            _IMAP_SERVER_OLD,
            folder=folder,
            skip=skip,
            top=top,
        )
        elapsed_ms = (time.monotonic() - _t0) * 1000
        logger.info(
            "IMAP (old): %d emails, %dms",
            len(emails),
            elapsed_ms,
        )
        return FetchResult(
            success=True,
            emails=emails,
            method=f"IMAP ({_IMAP_SERVER_OLD})",
            has_more=has_more,
        )
    except Exception as exc:
        logger.warning("IMAP (old) failed: %s", exc)

    # ── Step 4: IMAP password login fallback ──
    if imap_password:
        for server_name, server_host in (
            ("IMAP password (new)", _IMAP_SERVER_NEW),
            ("IMAP password (old)", _IMAP_SERVER_OLD),
        ):
            try:
                emails, has_more = fetch_emails_imap(
                    email_addr,
                    imap_password,
                    server_host,
                    folder=folder,
                    skip=skip,
                    top=top,
                    use_password=True,
                )
                elapsed_ms = (time.monotonic() - _t0) * 1000
                logger.info(
                    "%s: %d emails, %dms",
                    server_name,
                    len(emails),
                    elapsed_ms,
                )
                return FetchResult(
                    success=True,
                    emails=emails,
                    method=f"{server_name} ({server_host})",
                    has_more=has_more,
                )
            except Exception as exc:
                logger.warning("%s failed: %s", server_name, exc)

    elapsed_ms = (time.monotonic() - _t0) * 1000
    logger.error("All methods failed in %dms", elapsed_ms)
    return FetchResult(
        success=False,
        error="All fetch methods failed (Graph API + IMAP new + IMAP old)",
    )
