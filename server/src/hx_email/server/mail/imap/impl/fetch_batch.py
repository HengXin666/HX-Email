from __future__ import annotations

import email
import re

from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.imap.imap_helpers import (
    decode_mime_header,
    extract_flags_from_fetch,
    extract_from,
    extract_text_and_html,
    has_attachments,
    parse_date,
    recipient_from_envelope,
    strip_html,
)

FETCH_BATCH_SIZE: int = 50
UID_PATTERN: re.Pattern[bytes] = re.compile(rb"\bUID\s+(\d+)\b", re.IGNORECASE)


def chunk_uids(uids: list[bytes], size: int = FETCH_BATCH_SIZE) -> list[list[bytes]]:
    return [uids[index : index + size] for index in range(0, len(uids), size)]


def uid_set_for_fetch(uids: list[bytes]) -> str:
    return b",".join(uids).decode("ascii", errors="ignore")


def messages_from_fetch_data(
    fetch_data: list[object],
    fallback_uids: list[bytes],
    account: EmailAccountMailbox,
) -> list[MailboxMessage]:
    messages: list[MailboxMessage] = []
    fallback_index: int = 0
    for item in fetch_data:
        if not (isinstance(item, tuple) and len(item) >= 2):
            continue
        raw_email = item[1]
        if not isinstance(raw_email, bytes | bytearray):
            continue
        uid = uid_from_fetch_item(item) or fallback_uid(fallback_uids, fallback_index)
        fallback_index += 1
        messages.append(message_from_raw(bytes(raw_email), item, uid, account))
    return messages


def uid_from_fetch_item(item: tuple[object, ...]) -> str:
    meta = item[0]
    if not isinstance(meta, bytes | bytearray):
        meta = str(meta).encode()
    match = UID_PATTERN.search(bytes(meta))
    if match is None:
        return ""
    return match.group(1).decode("ascii", errors="ignore")


def fallback_uid(uids: list[bytes], index: int) -> str:
    if index >= len(uids):
        return ""
    return uids[index].decode("ascii", errors="ignore")


def message_from_raw(
    raw_email: bytes,
    fetch_item: tuple[object, ...],
    uid: str,
    account: EmailAccountMailbox,
) -> MailboxMessage:
    msg = email.message_from_bytes(raw_email)
    text_body, html_body = extract_text_and_html(msg)
    body_text = text_body or strip_html(html_body)
    flags_text = extract_flags_from_fetch(fetch_item)
    return MailboxMessage(
        recipient_address=recipient_from_envelope(msg, account.primary_address),
        subject=decode_mime_header(str(msg.get("subject") or "")),
        body=body_text,
        from_address=extract_from(msg),
        received_at=parse_date(msg.get("date")),
        message_id=uid,
        is_read="\\Seen" in flags_text,
        has_attachments=has_attachments(msg),
    )
