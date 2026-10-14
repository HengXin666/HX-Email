"""IMAP session layer: credentials, connection, folder selection, token exchange."""

from hx_email.server.mail.imap.session.credentials import (
    IMAP_HOSTS,
    IMAP_TIMEOUT_SECONDS,
    ImapCredentials,
    close_imap,
    connect_imap,
    login_imap,
    normalize_password,
    resolve_imap_credentials,
    resolve_oauth_token,
    select_imap_folder,
    send_imap_id,
)
from hx_email.server.mail.imap.session.fetch import IMAPMailboxProvider
from hx_email.server.mail.imap.session.oauth import (
    get_imap_token,
    try_get_imap_token,
)

__all__ = [
    "IMAP_HOSTS",
    "IMAP_TIMEOUT_SECONDS",
    "IMAPMailboxProvider",
    "ImapCredentials",
    "close_imap",
    "connect_imap",
    "get_imap_token",
    "login_imap",
    "normalize_password",
    "resolve_imap_credentials",
    "resolve_oauth_token",
    "select_imap_folder",
    "send_imap_id",
    "try_get_imap_token",
]
