"""IMAP credentials: resolve, connect, authenticate, select a folder.

Every IMAP path goes through here, so proxy handling, XOAUTH2 versus password auth
and folder-name candidates cannot drift apart between the features that read mail.
"""

from __future__ import annotations

import imaplib
import logging
import ssl
from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import decrypt_secret, persist_rotated_refresh_token
from hx_email.server.mail import EmailAccountMailbox
from hx_email.server.mail.google_oauth import get_google_access_token
from hx_email.server.mail.imap.helpers import _OUTLOOK_PROVIDERS
from hx_email.server.mail.imap.impl.folder_candidates import (
    get_imap_folder_candidates,
    normalize_folder_key,
)
from hx_email.server.mail.imap.impl.proxy import imap_connect_via_proxy, load_group_proxy
from hx_email.server.mail.imap.session.mailboxes import resolve_special_use_name
from hx_email.server.mail.imap.session.oauth import try_get_imap_token

logger = logging.getLogger(__name__)

IMAP_HOSTS: dict[str, str] = {
    "outlook": "outlook.live.com",
    "hotmail": "outlook.live.com",
    "gmail": "imap.gmail.com",
    "yahoo": "imap.mail.yahoo.com",
    "icloud": "imap.mail.me.com",
    "qq": "imap.qq.com",
    "163": "imap.163.com",
    "126": "imap.126.com",
}

IMAP_TIMEOUT_SECONDS: int = 30


def normalize_password(provider: str, password: str) -> str:
    """Normalize a password for the provider before IMAP/SMTP login.

    Gmail app passwords are 16 chars that Google displays grouped in fours, but
    IMAP/SMTP login requires them without spaces. Applied at the point of use so
    already-stored values (however they were entered) are accepted. Other providers
    keep the password verbatim.
    """
    if provider.strip().lower() == "gmail":
        return "".join(password.split())
    return password


@dataclass(frozen=True)
class ImapCredentials:
    """Everything needed to reach and authenticate one mailbox over IMAP."""

    host: str
    port: int
    username: str
    credential: str
    use_xoauth2: bool
    proxy_url: str


def resolve_imap_credentials(
    settings: Settings,
    account: EmailAccountMailbox,
) -> ImapCredentials | None:
    """Resolve host/port/credential for an account.

    Returns None when the account row is gone or no IMAP host is configured; raises
    when a host exists but neither a password nor OAuth credentials do, because a
    silent empty result there would look like "no mail" instead of a misconfiguration.
    """
    with connect(settings) as conn:
        row = conn.execute(
            "SELECT imap_host, imap_port, username, imap_password, "
            "client_id, refresh_token FROM email_accounts WHERE id = ?",
            (account.id,),
        ).fetchone()
    if row is None:
        return None
    imap_host: str = (row["imap_host"] or "").strip() or IMAP_HOSTS.get(account.provider, "")
    if not imap_host:
        return None
    imap_port: int = int(row["imap_port"]) if row["imap_port"] else 993
    username: str = (row["username"] or "").strip() or account.primary_address
    password: str = (row["imap_password"] or "").strip()
    client_id: str = (row["client_id"] or "").strip()
    refresh_token: str = decrypt_secret(settings, str(row["refresh_token"] or "")).strip()
    if (
        not password
        and refresh_token
        and not client_id
        and account.provider not in _OUTLOOK_PROVIDERS
    ):
        # Gmail app passwords are stored in the refresh_token column by legacy imports.
        password = refresh_token
    password = normalize_password(account.provider, password)
    proxy_url: str = load_group_proxy(settings, account.id)
    if proxy_url:
        logger.info("IMAP proxy=%s account=%d (%s)", proxy_url, account.id, account.primary_address)
    if client_id and refresh_token:
        access_token = resolve_oauth_token(
            settings, account, client_id, refresh_token, imap_host, proxy_url
        )
        return ImapCredentials(
            host=imap_host,
            port=imap_port,
            username=account.primary_address,
            credential=access_token,
            use_xoauth2=True,
            proxy_url=proxy_url,
        )
    if password:
        return ImapCredentials(
            host=imap_host,
            port=imap_port,
            username=username,
            credential=password,
            use_xoauth2=False,
            proxy_url=proxy_url,
        )
    raise RuntimeError("账户没有配置密码或 OAuth 凭证，无法连接 IMAP")  # noqa: RUF001


def connect_imap(credentials: ImapCredentials) -> imaplib.IMAP4:
    """Open an IMAP connection (TLS or STARTTLS, direct or through the group proxy)."""
    if credentials.proxy_url:
        logger.info(
            "IMAP via proxy %s -> %s:%d",
            credentials.proxy_url,
            credentials.host,
            credentials.port,
        )
        return imap_connect_via_proxy(
            credentials.proxy_url, credentials.host, credentials.port, IMAP_TIMEOUT_SECONDS
        )
    context = ssl.create_default_context()
    if credentials.port == 993:
        return imaplib.IMAP4_SSL(
            credentials.host,
            credentials.port,
            ssl_context=context,
            timeout=IMAP_TIMEOUT_SECONDS,
        )
    connection = imaplib.IMAP4(credentials.host, credentials.port, timeout=IMAP_TIMEOUT_SECONDS)
    connection.starttls(ssl_context=context)
    return connection


def login_imap(connection: imaplib.IMAP4, credentials: ImapCredentials) -> None:
    """Authenticate an open connection (XOAUTH2 or password) and send IMAP ID."""
    send_imap_id(connection)
    if credentials.use_xoauth2:
        auth_string = (
            f"user={credentials.username}\x01auth=Bearer {credentials.credential}\x01\x01"
        ).encode()
        connection.authenticate("XOAUTH2", lambda _: auth_string)
    else:
        connection.login(credentials.username, credentials.credential)
    logger.info("IMAP authenticated OK for %s", credentials.username)


def select_imap_folder(
    connection: imaplib.IMAP4,
    provider: str,
    folder: str,
    *,
    readonly: bool,
) -> str | None:
    """Select the first candidate name that exists, then the server's own name.

    The candidate table holds English names, which a localized account never matches
    ("[Gmail]/&V4NXPpCuTvY-" is Spam on a Chinese Gmail account), so when every
    candidate is refused the name is resolved from LIST's special-use attributes.
    """
    for name in get_imap_folder_candidates(provider, folder):
        selected = try_select(connection, name, readonly=readonly)
        if selected is not None:
            return selected
    resolved: str = resolve_special_use_name(connection, normalize_folder_key(folder))
    if resolved:
        return try_select(connection, resolved, readonly=readonly)
    return None


def try_select(connection: imaplib.IMAP4, name: str, *, readonly: bool) -> str | None:
    """Select one mailbox through its raw or quoted form; None when neither works."""
    for try_name in (name, f'"{name}"'):
        try:
            status, _data = connection.select(try_name, readonly=readonly)
            if status == "OK":
                return try_name
        except Exception:
            continue
    return None


def close_imap(connection: imaplib.IMAP4 | None) -> None:
    """Close and log out, swallowing the errors a dead connection raises."""
    if connection is None:
        return
    try:
        connection.close()
        connection.logout()
    except Exception:
        pass


def send_imap_id(connection: imaplib.IMAP4) -> None:
    """IMAP ID command (required by 163/126 NetEase); optional everywhere else."""
    try:
        imaplib.Commands["ID"] = ("NONAUTH", "AUTH", "SELECTED")
        connection._simple_command("ID", '("name" "hxemail" "version" "1.0")')
    except Exception:
        pass


def resolve_oauth_token(
    settings: Settings,
    account: EmailAccountMailbox,
    client_id: str,
    refresh_token: str,
    imap_host: str,
    proxy_url: str,
) -> str:
    """Exchange a refresh token for an IMAP access token (Google or Microsoft)."""
    if account.provider == "gmail":
        access_token = get_google_access_token(settings, client_id, refresh_token, proxy_url)
        logger.info(
            "IMAP token for %d (%s, tenant=google) -> %s",
            account.id,
            account.primary_address,
            imap_host,
        )
        return access_token
    access_token, tenant_used, rotated_token = try_get_imap_token(client_id, refresh_token)
    persist_rotated_refresh_token(settings, account.id, refresh_token, rotated_token)
    logger.info(
        "IMAP token for %d (%s, tenant=%s) -> %s",
        account.id,
        account.primary_address,
        tenant_used,
        imap_host,
    )
    return access_token
