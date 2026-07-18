"""GraphMailProvider — fetch emails via Microsoft Graph API for Outlook/Hotmail accounts."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import decrypt_secret
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.graph.graph_helpers import (
    _GRAPH_BASE_URL,
    graph_get,
    graph_message_id,
    parse_graph_message,
    try_get_graph_token,
)
from hx_email.server.mail.imap.impl.proxy import load_group_proxy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphReadResult:
    messages: list[MailboxMessage]
    succeeded: bool


class GraphMailProvider:
    """Fetch emails via Microsoft Graph API for Outlook/Hotmail accounts.

    Uses OAuth2 refresh_token → access_token → Graph API.
    Falls back to empty results when credentials are missing or Graph is unavailable.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ── public API ──────────────────────────────────────────────────────

    def read_messages(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        top: int = 50,
        since_uid: str = "",
    ) -> list[MailboxMessage]:
        """List recent messages from the given folder via Graph API."""
        _ = since_uid
        return self.read_messages_result(email_account, folder, top).messages

    def read_messages_result(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        top: int = 50,
    ) -> GraphReadResult:
        """List recent messages and report whether Graph was reached successfully."""
        row = self._load_account_row(email_account.id)
        if row is None:
            return GraphReadResult([], False)
        client_id, refresh_token = self._extract_credentials(row)
        refresh_token = decrypt_secret(self._settings, refresh_token)
        if not client_id or not refresh_token:
            return GraphReadResult([], False)
        proxy_url = load_group_proxy(self._settings, email_account.id)
        try:
            access_token, _tenant = try_get_graph_token(client_id, refresh_token, proxy_url)
        except RuntimeError as exc:
            logger.warning("Graph token failed for account %d: %s", email_account.id, exc)
            return GraphReadResult([], False)
        return self._graph_list_messages(access_token, email_account, folder, top, proxy_url)

    def read_message_detail(
        self,
        email_account: EmailAccountMailbox,
        message_id: str,
    ) -> MailboxMessage | None:
        """Get a single message by its Graph ID. Returns None if not found."""
        row = self._load_account_row(email_account.id)
        if row is None:
            return None
        client_id, refresh_token = self._extract_credentials(row)
        refresh_token = decrypt_secret(self._settings, refresh_token)
        if not client_id or not refresh_token:
            return None
        proxy_url = load_group_proxy(self._settings, email_account.id)
        try:
            access_token, _tenant = try_get_graph_token(client_id, refresh_token, proxy_url)
        except RuntimeError as exc:
            logger.warning("Graph token failed for account %d: %s", email_account.id, exc)
            return None
        return self._graph_get_message(access_token, email_account, message_id, proxy_url)

    # ── internal ────────────────────────────────────────────────────────

    def _load_account_row(self, account_id: int) -> sqlite3.Row | None:
        with connect(self._settings) as conn:
            row: sqlite3.Row | None = conn.execute(
                "SELECT client_id, refresh_token FROM email_accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            return row

    @staticmethod
    def _extract_credentials(row: sqlite3.Row) -> tuple[str, str]:
        return (str(row["client_id"] or "").strip(), str(row["refresh_token"] or "").strip())

    def _graph_list_messages(
        self,
        access_token: str,
        account: EmailAccountMailbox,
        folder: str,
        top: int,
        proxy_url: str = "",
    ) -> GraphReadResult:
        """Call Graph API to list messages in a folder."""
        folder_path = resolve_graph_folder(folder)
        query: str = urlencode(
            {
                "$top": str(top),
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,toRecipients,receivedDateTime,body",
            },
            quote_via=quote,
        )
        url: str = f"{_GRAPH_BASE_URL}/me/mailFolders/{folder_path}/messages?{query}"
        try:
            data = graph_get(url, access_token, proxy_url=proxy_url)
        except Exception as exc:
            logger.warning("Graph list messages failed for account %d: %s", account.id, exc)
            return GraphReadResult([], False)

        messages: list[MailboxMessage] = []
        items = data.get("value")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    messages.append(parse_graph_message(item, account.primary_address))
        return GraphReadResult(messages, True)

    def _graph_get_message(
        self,
        access_token: str,
        account: EmailAccountMailbox,
        message_id: str,
        proxy_url: str = "",
    ) -> MailboxMessage | None:
        """Call Graph API to get a single message by ID."""
        url = f"{_GRAPH_BASE_URL}/me/messages/{message_id}"
        try:
            data = graph_get(url, access_token, proxy_url=proxy_url)
        except Exception as exc:
            logger.warning(
                "Graph get message %s failed for account %d: %s",
                message_id,
                account.id,
                exc,
            )
            return None

        if not isinstance(data, dict) or not data:
            return None
        return parse_graph_message(data, account.primary_address)


def resolve_graph_folder(folder: str) -> str:
    """Map folder names to Graph API well-known folder names."""
    folder_lower = folder.lower().strip()
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
    return mapping.get(folder_lower, folder_lower)


def graph_list_message_ids(
    access_token: str,
    account: EmailAccountMailbox,
    folder: str,
    top: int = 50,
    proxy_url: str = "",
) -> list[str]:
    """List message IDs (lightweight — only fetches ids) via Graph API."""
    folder_path = resolve_graph_folder(folder)
    query: str = urlencode(
        {
            "$top": str(top),
            "$orderby": "receivedDateTime desc",
            "$select": "id",
        },
        quote_via=quote,
    )
    url: str = f"{_GRAPH_BASE_URL}/me/mailFolders/{folder_path}/messages?{query}"
    try:
        data = graph_get(url, access_token, proxy_url=proxy_url)
    except Exception:
        return []

    ids: list[str] = []
    items = data.get("value")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                msg_id = graph_message_id(item)
                if msg_id:
                    ids.append(msg_id)
    return ids
