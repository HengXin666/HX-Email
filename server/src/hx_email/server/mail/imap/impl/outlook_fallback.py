"""IMAP Outlook multi-server fallback — standalone function."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from hx_email.server.mail.imap.imap_helpers import _OUTLOOK_IMAP_SERVERS

if TYPE_CHECKING:
    from hx_email.server.mail import EmailAccountMailbox, MailboxMessage

logger = logging.getLogger(__name__)


def imap_fetch_outlook_fallback(
    fetch_fn: Callable[..., list[MailboxMessage]],
    primary_host: str,
    port: int,
    username: str,
    access_token: str,
    account: EmailAccountMailbox,
    proxy_url: str = "",
    *,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 50,
    since_uid: str = "",
) -> list[MailboxMessage]:
    """Try multiple Outlook IMAP servers, returning first successful result."""
    servers = [primary_host] + [s for s in _OUTLOOK_IMAP_SERVERS if s != primary_host]
    last_error: Exception | None = None
    for host in servers:
        try:
            logger.info("IMAP Outlook fallback: %s:%d for account %d", host, port, account.id)
            return fetch_fn(
                host,
                port,
                username,
                access_token,
                account,
                use_xoauth2=True,
                proxy_url=proxy_url,
                folder=folder,
                skip=skip,
                top=top,
                since_uid=since_uid,
            )
        except Exception as exc:
            logger.info("IMAP %s failed for %d: %s, trying next...", host, account.id, exc)
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("No Outlook IMAP servers available")
