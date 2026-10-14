"""IMAP MIME/header helpers shared by the fetch and delete paths.

Microsoft token exchange moved to ``imap_oauth`` (its former home here held a
second, live copy while ``imap_oauth`` held an unused duplicate).
"""

from __future__ import annotations

import email
import logging
from email.header import decode_header
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

_OUTLOOK_PROVIDERS: frozenset[str] = frozenset({"outlook", "hotmail"})
_OUTLOOK_IMAP_SERVERS: tuple[str, ...] = ("outlook.live.com", "outlook.office365.com")


class IMAPAuthRejectedError(RuntimeError):
    """IMAP XOAUTH2 auth rejected or OAuth-authenticated connection refused."""


def describe_imap_auth_error(
    error: str,
    host: str,
    use_xoauth2: bool,
) -> tuple[str, bool]:
    lowered: str = error.lower()
    if "authenticated but not connected" in lowered:
        return (
            f"OAuth auth OK but IMAP server {host} refused connection. "
            "Check account access and IMAP availability.",
            True,
        )
    auth_failed: bool = any(
        marker in lowered
        for marker in ("authenticationfailed", "authentication failed", "invalid credentials")
    )
    if use_xoauth2 and auth_failed:
        return (f"OAuth XOAUTH2 authentication rejected: {error}", True)
    if auth_failed or "login failed" in lowered:
        return (f"IMAP login failed (wrong password/app-password): {error}", False)
    return (error, False)


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
        if dt.tzinfo is not None:
            dt = dt.astimezone()
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


def has_attachments(msg: email.message.Message) -> bool:
    """Detect attachments via Content-Disposition header."""
    if not msg.is_multipart():
        return False
    for part in msg.walk():
        try:
            disp = str(part.get("Content-Disposition", "") or "").lower()
        except Exception:
            disp = ""
        if "attachment" in disp:
            return True
    return False


def extract_flags_from_fetch(fetch_item: object) -> str:
    """Extract IMAP flags string from a FETCH response item."""
    try:
        if isinstance(fetch_item, tuple) and fetch_item:
            meta = fetch_item[0]
            if isinstance(meta, bytes | bytearray):
                return meta.decode("utf-8", errors="ignore")
            return str(meta)
        if isinstance(fetch_item, bytes | bytearray):
            return fetch_item.decode("utf-8", errors="ignore")
        return str(fetch_item)
    except Exception:
        return ""


def strip_html(html_text: str) -> str:
    """Strip HTML tags, returning readable plain text."""
    if not html_text:
        return ""
    import re

    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text_and_html(msg: email.message.Message) -> tuple[str, str]:
    """Extract text/plain and text/html bodies, skipping attachments."""
    text_part = ""
    html_part = ""

    def _decode_payload(part: email.message.Message) -> str:
        try:
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            if isinstance(payload, bytes | bytearray):
                return payload.decode(charset, errors="replace")
            return str(payload) if payload is not None else ""
        except Exception:
            try:
                return str(part.get_payload())
            except Exception:
                return ""

    if msg.is_multipart():
        for part in msg.walk():
            try:
                disp = str(part.get("Content-Disposition", "") or "").lower()
            except Exception:
                disp = ""
            if "attachment" in disp:
                continue
            ct = (part.get_content_type() or "").lower()
            if ct == "text/plain" and not text_part:
                text_part = _decode_payload(part)
            elif ct == "text/html" and not html_part:
                html_part = _decode_payload(part)
            if text_part and html_part:
                break
    else:
        ct = (msg.get_content_type() or "").lower()
        if ct == "text/html":
            html_part = _decode_payload(msg)
        else:
            text_part = _decode_payload(msg)
    return text_part or "", html_part or ""
