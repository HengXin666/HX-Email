from __future__ import annotations

from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.impl.fetch.options import REFRESH_FOLDER_TOP, REFRESH_FOLDERS
from hx_email.server.mail.verification import FolderMailboxProvider, MailboxProvider, coerce_message


def read_refresh_messages(
    provider: MailboxProvider,
    account: EmailAccountMailbox,
) -> list[MailboxMessage | dict[str, object]]:
    if isinstance(provider, FolderMailboxProvider):
        messages: list[MailboxMessage | dict[str, object]] = []
        for folder in REFRESH_FOLDERS:
            messages.extend(
                provider.read_messages_folder(account, folder=folder, top=REFRESH_FOLDER_TOP)
            )
        return dedupe_messages(messages)
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
