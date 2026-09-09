from __future__ import annotations

from dataclasses import replace
from typing import Any

from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.impl.fetch.options import REFRESH_FOLDER_TOP, REFRESH_FOLDERS
from hx_email.server.mail.verification import MailboxProvider, coerce_message


def read_refresh_messages(
    provider: MailboxProvider,
    account: EmailAccountMailbox,
    latest_uid: str = "",
) -> list[MailboxMessage | dict[str, object]]:
    """按 REFRESH_FOLDERS 逐个文件夹读取 (收件箱 + 垃圾邮件箱), 去重后返回。"""
    messages: list[MailboxMessage | dict[str, object]] = []
    for folder in REFRESH_FOLDERS:
        messages.extend(read_folder_with_window(provider, account, folder, latest_uid))
    return dedupe_messages(messages)


def read_folder_with_window(
    provider: MailboxProvider,
    account: EmailAccountMailbox,
    folder: str,
    latest_uid: str,
) -> list[MailboxMessage]:
    """读单个文件夹。

    优先用 FolderMailboxProvider.read_messages_folder (IMAP/测试假件都实现了它);
    没有该方法的 provider (如 Graph→IMAP 的 FallbackMailProvider) 回落到
    read_messages(folder=...)。两种形态都兼容。

    增量 UID 只对收件箱有效: 垃圾箱是另一套 UID 空间, 传收件箱的 latest_uid
    会让垃圾箱永远读不到新信 (2026-09-09 实测)。
    """
    since_uid: str = latest_uid if folder == "inbox" else ""
    raw: list[Any]
    reader = getattr(provider, "read_messages_folder", None)
    if callable(reader):
        try:
            raw = reader(account, folder=folder, top=REFRESH_FOLDER_TOP, since_uid=since_uid)
        except TypeError:
            raw = reader(account, folder=folder, top=REFRESH_FOLDER_TOP)
    else:
        try:
            raw = provider.read_messages(
                account, folder=folder, top=REFRESH_FOLDER_TOP, since_uid=since_uid
            )
        except TypeError:
            raw = provider.read_messages(account)
    return tag_folder(list(raw), folder)


def tag_folder(
    messages: list[MailboxMessage | dict[str, object]],
    folder: str,
) -> list[MailboxMessage]:
    """给某个文件夹读出来的消息打来源标记 (MailboxMessage 是 frozen dataclass)。"""
    tagged: list[MailboxMessage] = []
    for raw in messages:
        message = coerce_message(raw)
        tagged.append(message if message.folder == folder else replace(message, folder=folder))
    return tagged


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
