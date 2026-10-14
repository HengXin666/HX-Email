from __future__ import annotations

import imaplib
import logging
import ssl

from hx_email.config import Settings
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.imap.helpers import (
    _OUTLOOK_IMAP_SERVERS,
    _OUTLOOK_PROVIDERS,
    IMAPAuthRejectedError,
    describe_imap_auth_error,
)
from hx_email.server.mail.imap.impl.fetch_batch import (
    chunk_uids,
    filter_uids_since,
    messages_from_fetch_data,
    uid_set_for_fetch,
)
from hx_email.server.mail.imap.impl.folder_candidates import get_imap_folder_candidates
from hx_email.server.mail.imap.impl.outlook_fallback import imap_fetch_outlook_fallback
from hx_email.server.mail.imap.session.credentials import (
    IMAP_HOSTS,
    ImapCredentials,
    close_imap,
    connect_imap,
    login_imap,
    resolve_imap_credentials,
    select_imap_folder,
)

logger = logging.getLogger(__name__)


class IMAPMailboxProvider:
    """Read messages over IMAP for any configured provider.

    Credential resolution, connect and folder selection live in
    ``session.credentials`` so the delete path reuses them verbatim.
    """

    _IMAP_HOSTS: dict[str, str] = IMAP_HOSTS

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout = 30

    def read_messages(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
        since_uid: str = "",
    ) -> list[MailboxMessage]:
        return self._fetch_messages(
            email_account,
            folder=folder,
            skip=skip,
            top=top,
            since_uid=since_uid,
        )

    def read_messages_folder(
        self,
        email_account: EmailAccountMailbox,
        *,
        folder: str,
        top: int,
        skip: int = 0,
        since_uid: str = "",
    ) -> list[MailboxMessage]:
        return self.read_messages(
            email_account,
            folder=folder,
            skip=skip,
            top=top,
            since_uid=since_uid,
        )

    def _fetch_messages(
        self,
        account: EmailAccountMailbox,
        *,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
        since_uid: str = "",
    ) -> list[MailboxMessage]:
        credentials = self.resolve_credentials(account)
        if credentials is None:
            return []
        if account.provider in _OUTLOOK_PROVIDERS or credentials.host in _OUTLOOK_IMAP_SERVERS:
            return imap_fetch_outlook_fallback(
                self._imap_fetch,
                credentials.host,
                credentials.port,
                credentials.username,
                credentials.credential,
                account,
                credentials.proxy_url,
                folder=folder,
                skip=skip,
                top=top,
                since_uid=since_uid,
            )
        return self._imap_fetch(
            credentials.host,
            credentials.port,
            credentials.username,
            credentials.credential,
            account,
            use_xoauth2=credentials.use_xoauth2,
            proxy_url=credentials.proxy_url,
            folder=folder,
            skip=skip,
            top=top,
            since_uid=since_uid,
        )

    def resolve_credentials(self, account: EmailAccountMailbox) -> ImapCredentials | None:
        """Resolve this account endpoint and credential (None = no host configured)."""
        return resolve_imap_credentials(self._settings, account)

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
        since_uid: str = "",
    ) -> list[MailboxMessage]:
        messages: list[MailboxMessage] = []
        conn: imaplib.IMAP4 | None = None
        skip = max(0, skip)
        top = max(1, top)
        credentials = ImapCredentials(
            host=host,
            port=port,
            username=username,
            credential=credential,
            use_xoauth2=use_xoauth2,
            proxy_url=proxy_url,
        )
        try:
            conn = connect_imap(credentials)
            login_imap(conn, credentials)
            selected = select_imap_folder(conn, account.provider, folder, readonly=True)
            if selected is None:
                candidates = get_imap_folder_candidates(account.provider, folder)
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
            uids = filter_uids_since(uids, since_uid)
            total = len(uids)
            start_idx = max(0, total - skip - top)
            end_idx = total - skip
            if start_idx >= end_idx:
                return messages
            paged_uids = uids[start_idx:end_idx][::-1]
            logger.info(
                "IMAP %d total, fetching %d (skip=%d top=%d)", total, len(paged_uids), skip, top
            )
            for uid_batch in chunk_uids(paged_uids):
                try:
                    f_status, f_data = conn.uid(
                        "FETCH", uid_set_for_fetch(uid_batch), "(UID FLAGS RFC822)"
                    )
                    if f_status != "OK" or not f_data:
                        continue
                    messages.extend(messages_from_fetch_data(f_data, uid_batch, account))
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
            error_str, auth_rejected = describe_imap_auth_error(str(exc), host, use_xoauth2)
            if auth_rejected:
                raise IMAPAuthRejectedError(error_str) from exc
            logger.warning("IMAP error %s:%d user=%s: %s", host, port, username, exc)
            raise RuntimeError(error_str) from exc
        finally:
            close_imap(conn)
        return messages
