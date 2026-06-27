"""FallbackMailProvider — Graph-first, IMAP-fallback for Outlook/Hotmail accounts.

Injects into the MailboxProvider protocol so ALL consumers (routes, background fetch,
verification, external API) automatically get Graph API support for Outlook accounts.
"""

from __future__ import annotations

import logging
from typing import Any

from hx_email.config import Settings
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.graph.graph_client import GraphMailProvider
from hx_email.server.mail.imap.imap_provider import IMAPMailboxProvider
from hx_email.server.mail.verification import coerce_message

logger = logging.getLogger(__name__)

_OUTLOOK_PROVIDERS: frozenset[str] = frozenset({"outlook", "hotmail"})


class FallbackMailProvider:
    """Graph → IMAP fallback provider implementing MailboxProvider protocol.

    For Outlook/Hotmail accounts with OAuth credentials, tries Graph API first.
    Falls back to IMAP on any failure.  Non-Outlook accounts use IMAP directly.

    Usage in app.py:
        provider = FallbackMailProvider(settings)
        create_app(settings, mailbox_provider=provider)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph = GraphMailProvider(settings)
        self._imap = IMAPMailboxProvider(settings)

    # ── MailboxProvider protocol ─────────────────────────────────────────

    def read_messages(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
    ) -> list[MailboxMessage | dict[str, object]]:
        """Fetch messages with Graph→IMAP fallback for Outlook accounts."""
        if email_account.provider in _OUTLOOK_PROVIDERS:
            graph_msgs = self._try_graph_read(email_account, folder=folder, top=top)
            if graph_msgs is not None:
                return graph_msgs  # type: ignore[return-value]
        return self._imap.read_messages(email_account, folder=folder, skip=skip, top=top)  # type: ignore[return-value]

    # ── extended API (not in protocol, used directly by email_service) ───

    def read_message_detail(
        self,
        email_account: EmailAccountMailbox,
        message_id: str,
    ) -> MailboxMessage | None:
        """Get single message detail. Graph-first for Outlook, IMAP for others."""
        if email_account.provider in _OUTLOOK_PROVIDERS:
            msg = self._graph.read_message_detail(email_account, message_id)
            if msg is not None:
                return msg
            # Graph failed — fall through to IMAP positional index
            return self._imap_read_detail_by_index(email_account, message_id)

        return self._imap_read_detail_by_index(email_account, message_id)

    def read_messages_with_method(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        top: int = 50,
        skip: int = 0,
    ) -> tuple[list[MailboxMessage], str]:
        """Fetch messages and return (messages, method_used)."""
        if email_account.provider in _OUTLOOK_PROVIDERS:
            graph_result = self._graph.read_messages_result(email_account, folder=folder, top=top)
            if graph_result.succeeded:
                return graph_result.messages, "graph"
            imap_msgs = self._imap.read_messages(email_account, folder=folder, skip=skip, top=top)
            return [coerce_message(m) for m in imap_msgs], "imap"
        imap_msgs = self._imap.read_messages(email_account, folder=folder, skip=skip, top=top)
        return [coerce_message(m) for m in imap_msgs], "imap"

    # ── internal ─────────────────────────────────────────────────────────

    def _try_graph_read(
        self, email_account: EmailAccountMailbox, *, folder: str = "inbox", top: int = 50
    ) -> list[MailboxMessage] | None:
        """Try Graph API read; returns None if Graph is unavailable or fails."""
        try:
            result = self._graph.read_messages_result(email_account, folder=folder, top=top)
            if result.succeeded:
                return result.messages
        except Exception as exc:
            logger.debug(
                "Graph read_messages failed for %s, falling back to IMAP: %s",
                email_account.primary_address,
                exc,
            )
        return None

    def _imap_read_detail_by_index(
        self,
        email_account: EmailAccountMailbox,
        message_id: str,
    ) -> MailboxMessage | None:
        """Read message detail via IMAP using positional index."""
        raw_messages: list[Any] = self._imap.read_messages(email_account)
        try:
            msg_idx = int(message_id) - 1
            if 0 <= msg_idx < len(raw_messages):
                return coerce_message(raw_messages[msg_idx])
        except (ValueError, IndexError):
            pass
        return None
