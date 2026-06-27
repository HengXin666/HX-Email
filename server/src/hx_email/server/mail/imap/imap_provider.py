from __future__ import annotations

import email
import imaplib
import logging
import ssl
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    pass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.imap.imap_helpers import (
    _OUTLOOK_PROVIDERS,
    decode_mime_header,
    extract_flags_from_fetch,
    extract_from,
    extract_text_and_html,
    has_attachments,
    parse_date,
    recipient_from_envelope,
    strip_html,
    try_get_imap_token,
)
from hx_email.server.mail.imap.impl.folder_candidates import get_imap_folder_candidates
from hx_email.server.mail.imap.impl.outlook_fallback import imap_fetch_outlook_fallback
from hx_email.server.mail.imap.impl.proxy import imap_connect_via_proxy, load_group_proxy

logger = logging.getLogger(__name__)


class IMAPAuthRejectedError(RuntimeError):
    """IMAP XOAUTH2 auth rejected — token valid but server refused connection."""


class IMAPMailboxProvider:
    _IMAP_HOSTS: ClassVar[dict[str, str]] = {
        "outlook": "outlook.live.com",
        "hotmail": "outlook.live.com",
        "gmail": "imap.gmail.com",
        "yahoo": "imap.mail.yahoo.com",
        "icloud": "imap.mail.me.com",
        "qq": "imap.qq.com",
        "163": "imap.163.com",
        "126": "imap.126.com",
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout = 30

    def read_messages(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
    ) -> list[MailboxMessage]:
        return self._fetch_messages(email_account, folder=folder, skip=skip, top=top)

    def _fetch_messages(
        self, account: EmailAccountMailbox, *, folder: str = "inbox", skip: int = 0, top: int = 50
    ) -> list[MailboxMessage]:
        with connect(self._settings) as conn:
            row = conn.execute(
                "SELECT imap_host, imap_port, username, imap_password, "
                "client_id, refresh_token FROM email_accounts WHERE id = ?",
                (account.id,),
            ).fetchone()
        if row is None:
            return []
        imap_host: str = (row["imap_host"] or "").strip() or self._IMAP_HOSTS.get(
            account.provider, ""
        )
        if not imap_host:
            return []
        imap_port = int(row["imap_port"]) if row["imap_port"] else 993
        username: str = (row["username"] or "").strip() or account.primary_address
        password: str = (row["imap_password"] or "").strip()
        client_id: str = (row["client_id"] or "").strip()
        refresh_token: str = (row["refresh_token"] or "").strip()
        proxy_url: str = load_group_proxy(self._settings, account.id)
        if proxy_url:
            logger.info(
                "IMAP proxy=%s account=%d (%s)", proxy_url, account.id, account.primary_address
            )
        if client_id and refresh_token:
            access_token, tenant_used = try_get_imap_token(client_id, refresh_token)
            logger.info(
                "IMAP token for %d (%s, tenant=%s) -> %s:%d",
                account.id,
                account.primary_address,
                tenant_used,
                imap_host,
                imap_port,
            )
            if account.provider in _OUTLOOK_PROVIDERS:
                return imap_fetch_outlook_fallback(
                    self._imap_fetch,
                    imap_host,
                    imap_port,
                    username,
                    access_token,
                    account,
                    proxy_url,
                    folder=folder,
                    skip=skip,
                    top=top,
                )
            return self._imap_fetch(
                imap_host,
                imap_port,
                username,
                access_token,
                account,
                use_xoauth2=True,
                proxy_url=proxy_url,
                folder=folder,
                skip=skip,
                top=top,
            )
        if password:
            return self._imap_fetch(
                imap_host,
                imap_port,
                username,
                password,
                account,
                use_xoauth2=False,
                proxy_url=proxy_url,
                folder=folder,
                skip=skip,
                top=top,
            )
        raise RuntimeError("账户没有配置密码或 OAuth 凭证，无法连接 IMAP")  # noqa: RUF001

    def _imap_fetch(
        self,
        host: str,
        port: int,
        username: str,
        credential: str,
        account: EmailAccountMailbox,
        *,
        use_xoauth2: bool = False,
        proxy_url: str = "",
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
    ) -> list[MailboxMessage]:
        messages: list[MailboxMessage] = []
        conn: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        skip = max(0, skip)
        top = max(1, top)
        try:
            # Connect (direct or via proxy)
            if proxy_url:
                logger.info("IMAP via proxy %s -> %s:%d", proxy_url, host, port)
                conn = imap_connect_via_proxy(proxy_url, host, port, self._timeout)
            elif port == 993:
                ctx = ssl.create_default_context()
                conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=self._timeout)
            else:
                ctx = ssl.create_default_context()
                conn = imaplib.IMAP4(host, port, timeout=self._timeout)
                conn.starttls(ssl_context=ctx)
            # IMAP ID command (required by 163/126 NetEase)
            try:
                imaplib.Commands["ID"] = ("NONAUTH", "AUTH", "SELECTED")
                conn._simple_command("ID", '("name" "hxemail" "version" "1.0")')
            except Exception:
                pass
            if use_xoauth2:
                auth_string = f"user={username}\x01auth=Bearer {credential}\x01\x01".encode()
                conn.authenticate("XOAUTH2", lambda _: auth_string)
            else:
                conn.login(username, credential)
            logger.info("IMAP authenticated OK for %s", username)

            # Resolve folder with provider-specific candidates
            candidates = get_imap_folder_candidates(account.provider, folder)
            selected: str | None = None
            for name in candidates:
                for try_name in (name, f'"{name}"'):
                    try:
                        status, _data = conn.select(try_name, readonly=True)
                        if status == "OK":
                            selected = try_name
                            break
                    except Exception:
                        continue
                if selected:
                    break
            if not selected:
                raise RuntimeError(
                    f"IMAP folder not found: folder={folder} candidates={candidates}"
                )

            # UID SEARCH → UID FETCH with pagination
            status, data = conn.uid("SEARCH", None, "ALL")  # type: ignore[arg-type]
            if status != "OK":
                raise RuntimeError(f"IMAP UID SEARCH failed: {status}")
            uid_bytes = data[0] if data and data[0] else b""
            if not uid_bytes:
                return messages
            uids: list[bytes] = uid_bytes.split()
            total = len(uids)
            # Paginate: newest first, slice by skip/top
            start_idx = max(0, total - skip - top)
            end_idx = total - skip
            if start_idx >= end_idx:
                return messages
            paged_uids = uids[start_idx:end_idx][::-1]
            logger.info(
                "IMAP %d total, fetching %d (skip=%d top=%d)", total, len(paged_uids), skip, top
            )
            for uid in paged_uids:
                try:
                    f_status, f_data = conn.uid("FETCH", uid, "(FLAGS RFC822)")  # type: ignore[arg-type]
                    if f_status != "OK" or not f_data:
                        continue
                    raw_email: bytes | None = None
                    flags_text = ""
                    for item in f_data:
                        if isinstance(item, tuple) and len(item) >= 2:
                            flags_text = extract_flags_from_fetch(item)
                            raw_email = item[1]
                            break
                    if not raw_email:
                        continue
                    msg = email.message_from_bytes(raw_email)
                    text_body, html_body = extract_text_and_html(msg)
                    body_text = text_body or strip_html(html_body)
                    uid_str = uid.decode("ascii") if isinstance(uid, bytes) else str(uid)
                    messages.append(
                        MailboxMessage(
                            recipient_address=recipient_from_envelope(msg, account.primary_address),
                            subject=decode_mime_header(str(msg.get("subject") or "")),
                            body=body_text,
                            from_address=extract_from(msg),
                            received_at=parse_date(msg.get("date")),
                            message_id=uid_str,
                            is_read="\\Seen" in flags_text,
                            has_attachments=has_attachments(msg),
                        )
                    )
                except Exception:
                    continue
            logger.info("IMAP parsed %d messages for account %d", len(messages), account.id)
        except (
            TimeoutError,
            imaplib.IMAP4.error,
            imaplib.IMAP4.abort,
            ConnectionError,
            ssl.SSLError,
            OSError,
        ) as exc:
            error_str = str(exc)
            if "authenticated but not connected" in error_str.lower():
                error_str = (
                    f"OAuth auth OK but IMAP server {host} refused connection. "
                    "Check: 1) IMAP/POP3 enabled; 2) account not locked; "
                    "3) new account needs web login first; 4) try alternate IMAP server."
                )
                raise IMAPAuthRejectedError(error_str) from exc
            if "login failed" in error_str.lower() or "authentication failed" in error_str.lower():
                error_str = f"IMAP login failed (wrong password/app-password): {error_str}"
            logger.warning("IMAP error %s:%d user=%s: %s", host, port, username, exc)
            raise RuntimeError(error_str) from exc
        finally:
            if conn is not None:
                try:
                    conn.close()
                    conn.logout()
                except Exception:
                    pass
        return messages
