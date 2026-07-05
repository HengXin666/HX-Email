from __future__ import annotations

from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.impl.fetch.options import REFRESH_FOLDER_TOP, REFRESH_FOLDERS
from hx_email.server.mail.verification import FolderMailboxProvider, MailboxProvider, coerce_message


def read_refresh_messages(
    provider: MailboxProvider,
    account: EmailAccountMailbox,
    latest_uid: str = "",
) -> list[MailboxMessage | dict[str, object]]:
    if isinstance(provider, FolderMailboxProvider):
        messages: list[MailboxMessage | dict[str, object]] = []
        for folder in REFRESH_FOLDERS:
            messages.extend(read_folder_with_window(provider, account, folder, latest_uid))
        return dedupe_messages(messages)
    return read_messages_with_window(provider, account, latest_uid)


def read_folder_with_window(
    provider: FolderMailboxProvider,
    account: EmailAccountMailbox,
    folder: str,
    latest_uid: str,
) -> list[MailboxMessage | dict[str, object]]:
    try:
        return provider.read_messages_folder(
            account,
            folder=folder,
            top=REFRESH_FOLDER_TOP,
            since_uid=latest_uid,
        )
    except TypeError:
        return provider.read_messages_folder(account, folder=folder, top=REFRESH_FOLDER_TOP)


def read_messages_with_window(
    provider: MailboxProvider,
    account: EmailAccountMailbox,
    latest_uid: str = "",
) -> list[MailboxMessage | dict[str, object]]:
    try:
        return provider.read_messages(account, top=REFRESH_FOLDER_TOP, since_uid=latest_uid)
    except TypeError:
        return provider.read_messages(account)


def dedupe_messages(
    messages: list[MailboxMessage | dict[str, object]],
) -> list[MailboxMessage | dict[str, object]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[MailboxMessage | dict[str, object]] = []
    for raw in messages:
        msg = coerce_message(raw)
        key = (msg.message_id, msg.subject, msg.received_at)
        if key in seen:
            continue
        seen.add(key)
        unique.append(raw)
    return unique
