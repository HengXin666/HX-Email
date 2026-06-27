"""IMAP proxy helpers — group proxy lookup and HTTP CONNECT tunneling."""

from __future__ import annotations

import imaplib
import logging
import socket
import ssl as _ssl
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hx_email.config import Settings

logger = logging.getLogger(__name__)


def load_group_proxy(settings: Settings, account_id: int) -> str:
    """Look up proxy_url from the group linked to this account.

    Checks usable_emails (any kind) first, then falls back to email_accounts.group_id.
    """
    from hx_email.database import connect as _connect

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
            logger.info(
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
            logger.info(
                "load_group_proxy(account=%d): found via email_accounts.group_id -> %s",
                account_id,
                result,
            )
            return result
    logger.warning("load_group_proxy(account=%d): no proxy found", account_id)
    return ""


def imap_connect_via_proxy(
    proxy_url: str, host: str, port: int, timeout: int = 30
) -> imaplib.IMAP4:
    """Create an IMAP4 connection through an HTTP CONNECT proxy tunnel."""
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
