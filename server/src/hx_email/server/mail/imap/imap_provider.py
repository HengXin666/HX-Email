from __future__ import annotations

import email
import imaplib
import logging
import ssl
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import sqlite3
from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail import (
    EmailAccountMailbox,
    MailboxMessage,
)
from hx_email.server.mail.imap.imap_helpers import (
    _OUTLOOK_IMAP_SERVERS,
    _OUTLOOK_PROVIDERS,
    decode_mime_header,
    extract_from,
    get_body,
    imap_connect_via_proxy,
    load_group_proxy,
    parse_date,
    recipient_from_envelope,
    try_get_imap_token,
)

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

    def read_messages(self, email_account: EmailAccountMailbox) -> list[MailboxMessage]:
        return self._fetch_messages(email_account)

    def _fetch_messages(self, account: EmailAccountMailbox) -> list[MailboxMessage]:
        row = self._load_account_row(account.id)
        if row is None:
            return []
        imap_host: str = (row["imap_host"] or "").strip()
        if not imap_host:
            imap_host = self._IMAP_HOSTS.get(account.provider, "")
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
                "IMAP token obtained for account %d (%s, tenant=%s), connecting to %s:%d",
                account.id,
                account.primary_address,
                tenant_used,
                imap_host,
                imap_port,
            )
            if account.provider in _OUTLOOK_PROVIDERS:
                return self._imap_fetch_outlook_fallback(
                    imap_host, imap_port, username, access_token, account, proxy_url
                )
            return self._imap_fetch(
                imap_host,
                imap_port,
                username,
                access_token,
                account,
                use_xoauth2=True,
                proxy_url=proxy_url,
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
            )
        raise RuntimeError("账户没有配置密码或 OAuth 凭证，无法连接 IMAP")  # noqa: RUF001

    def _imap_fetch_outlook_fallback(
        self,
        primary_host: str,
        port: int,
        username: str,
        access_token: str,
        account: EmailAccountMailbox,
        proxy_url: str = "",
    ) -> list[MailboxMessage]:
        servers: list[str] = [primary_host]
        for alt in _OUTLOOK_IMAP_SERVERS:
            if alt not in servers:
                servers.append(alt)
        last_error: Exception | None = None
        for host in servers:
            try:
                logger.info(
                    "IMAP Outlook fallback: trying %s:%d for account %d",
                    host,
                    port,
                    account.id,
                )
                return self._imap_fetch(
                    host,
                    port,
                    username,
                    access_token,
                    account,
                    use_xoauth2=True,
                    proxy_url=proxy_url,
                )
            except Exception as exc:
                logger.info(
                    "IMAP server %s failed for account %d: %s, trying next...",
                    host,
                    account.id,
                    exc,
                )
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("No Outlook IMAP servers available")

    def _load_account_row(self, account_id: int) -> sqlite3.Row | None:
        with connect(self._settings) as conn:
            sql: str = "SELECT imap_host, imap_port, username, imap_password, "
            sql += "client_id, refresh_token FROM email_accounts WHERE id = ?"
            return conn.execute(sql, (account_id,)).fetchone()  # type: ignore[no-any-return]

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
    ) -> list[MailboxMessage]:
        messages: list[MailboxMessage] = []
        conn: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
        auth_method = "XOAUTH2" if use_xoauth2 else "password"
        try:
            ctx = ssl.create_default_context()
            if proxy_url:
                logger.info(
                    "IMAP connecting via proxy %s to %s:%d (user=%s, auth=%s)",
                    proxy_url,
                    host,
                    port,
                    username,
                    auth_method,
                )
                conn = imap_connect_via_proxy(proxy_url, host, port, self._timeout)
            else:
                logger.info(
                    "IMAP connecting to %s:%d (user=%s, auth=%s)", host, port, username, auth_method
                )
                if port == 993:
                    conn = imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=self._timeout)
                else:
                    conn = imaplib.IMAP4(host, port, timeout=self._timeout)
                    conn.starttls(ssl_context=ctx)
            if use_xoauth2:
                auth_string = f"user={username}\x01auth=Bearer {credential}\x01\x01".encode()
                conn.authenticate("XOAUTH2", lambda _: auth_string)
            else:
                conn.login(username, credential)
            logger.info("IMAP authenticated OK for %s", username)
            status: str = "NO"
            select_data: Any = None
            for folder_name in ('"INBOX"', "INBOX"):
                try:
                    status, select_data = conn.select(folder_name, readonly=True)
                    if status == "OK":
                        break
                except Exception:
                    continue
            logger.info("IMAP select INBOX: status=%s, data=%s", status, select_data)
            if status != "OK":
                raise RuntimeError(f"IMAP SELECT INBOX failed: {status}")
            status, data = conn.search(None, "ALL")
            logger.info(
                "IMAP search ALL: status=%s, data=%s",
                status,
                data[0][:100] if data and data[0] else data,
            )
            if status != "OK" or not data:
                return messages
            all_ids = data[0].split()
            recent_ids = all_ids[-50:] if len(all_ids) > 50 else all_ids
            logger.info(
                "IMAP found %d total messages, fetching %d recent", len(all_ids), len(recent_ids)
            )
            if not recent_ids:
                return messages
            id_range = b",".join(recent_ids).decode("ascii")
            status, fetch_data = conn.fetch(id_range, "(RFC822)")
            logger.info("IMAP fetch %d messages: status=%s", len(recent_ids), status)
            if status != "OK" or not fetch_data:
                raise RuntimeError(f"IMAP FETCH failed: {status}")
            parsed_count = 0
            for item in fetch_data:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                raw = item[1]
                if raw is None:
                    continue
                try:
                    msg = email.message_from_bytes(raw)
                except Exception:
                    continue
                messages.append(
                    MailboxMessage(
                        recipient_address=recipient_from_envelope(msg, account.primary_address),
                        subject=decode_mime_header(str(msg.get("subject") or "")),
                        body=get_body(msg),
                        from_address=extract_from(msg),
                        received_at=parse_date(msg.get("date")),
                    )
                )
                parsed_count += 1
            logger.info("IMAP parsed %d messages for account %d", parsed_count, account.id)
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
                    f"OAuth 认证成功但 IMAP 服务器 {host} 拒绝连接。"
                    "该账号可能：1) 未开启 IMAP/POP3；"  # noqa: RUF001
                    "2) 被微软风控锁定；"  # noqa: RUF001
                    "3) 新账号需先通过网页登录激活。"
                    "4) 可尝试在邮箱设置中切换 IMAP 服务器地址。"
                )
                logger.warning(
                    "IMAP protocol error for %s:%d user=%s auth=%s: %s",
                    host,
                    port,
                    username,
                    auth_method,
                    exc,
                )
                raise IMAPAuthRejectedError(error_str) from exc
            if "login failed" in error_str.lower() or "authentication failed" in error_str.lower():
                error_str = f"IMAP 登录失败（密码/授权码可能错误）: {error_str}"  # noqa: RUF001
            logger.warning(
                "IMAP protocol error for %s:%d user=%s auth=%s: %s",
                host,
                port,
                username,
                auth_method,
                exc,
            )
            raise RuntimeError(error_str) from exc
        finally:
            if conn is not None:
                try:
                    conn.close()
                    conn.logout()
                except Exception:
                    pass
        return messages
