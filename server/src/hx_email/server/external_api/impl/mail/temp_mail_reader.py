"""Temp-mail aware reading for external API mail operations.

Real mailbox accounts resolve through ``email_accounts``; temp mailboxes
(``usable_emails.kind = 'temp'``) have no account row and must be read
through the temp mail provider (e.g. the CF Worker). This module bridges
temp mail messages into the same ``MailboxMessage`` pipeline used by the
rest of the external mail services, merging text + html so HTML-only
messages (e.g. Microsoft security codes) still yield verification codes.
"""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.external_api.impl.mail.helpers import (
    build_summary,
    filter_messages,
)
from hx_email.server.mail import MailboxMessage
from hx_email.server.mail.temp_mail import (
    MissingTempMailProviderError,
    TempMailbox,
    TempMailMessage,
    TempMailProvider,
    get_temp_mailbox,
    list_temp_messages,
)


def find_temp_mailbox(
    settings: Settings,
    email: str,
) -> tuple[int, TempMailbox] | None:
    """Look up an active temp mailbox by delivery address, or None."""
    from hx_email.server.mail.verification.addresses import normalize_delivery_address

    target: str = normalize_delivery_address(email)
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT ue.id, ue.user_id, ue.address
            FROM usable_emails ue
            JOIN temp_mailboxes tm ON tm.usable_email_id = ue.id
            WHERE ue.kind = 'temp' AND ue.active = 1 AND ue.status = 'active'
            """,
        ).fetchall()
    for row in rows:
        if normalize_delivery_address(str(row["address"] or "")) != target:
            continue
        user_id: int = int(row["user_id"])
        mailbox = get_temp_mailbox(settings, user_id, int(row["id"]))
        if mailbox is not None:
            return user_id, mailbox
    return None


def read_temp_messages(
    settings: Settings,
    user_id: int,
    mailbox: TempMailbox,
    temp_mail_providers: dict[str, TempMailProvider],
) -> tuple[TempMailMessage, ...]:
    """Fetch messages from the temp mail provider for a mailbox."""
    try:
        return list_temp_messages(
            settings,
            user_id,
            mailbox.usable_email_id,
            temp_mail_providers,
        )
    except MissingTempMailProviderError:
        # Provider is no longer configured: behave like an empty mailbox
        # instead of surfacing an internal error to external API consumers.
        return ()


def to_mailbox_messages(
    messages: tuple[TempMailMessage, ...],
    recipient_address: str,
) -> list[MailboxMessage]:
    """Convert temp mail messages to the shared MailboxMessage shape.

    text + html are merged so code/link extraction also sees HTML-only
    bodies (providers frequently render the body only as HTML).
    """
    converted: list[MailboxMessage] = []
    for message in messages:
        body: str = message.text or ""
        if message.html:
            body = f"{body}\n{message.html}" if body else message.html
        converted.append(
            MailboxMessage(
                recipient_address=recipient_address,
                subject=message.subject,
                body=body,
                from_address=message.from_address,
                from_email=message.from_address,
                body_html=message.html or "",
                received_at=message.received_at,
                message_id=message.id,
            )
        )
    return converted


def _find_message_index(
    messages: tuple[TempMailMessage, ...],
    message_id: str,
) -> int:
    """Return provider position for a message id; supports 1-based indices."""
    for index, message in enumerate(messages):
        if message.id == message_id:
            return index
    try:
        index = int(message_id) - 1
        if 0 <= index < len(messages):
            return index
    except ValueError:
        pass
    return -1


def temp_get_messages(
    settings: Settings,
    email: str,
    temp_mail_providers: dict[str, TempMailProvider],
    skip: int,
    top: int,
    from_contains: str | None,
    subject_contains: str | None,
    since_minutes: int | None,
) -> dict[str, object] | None:
    """List temp mail messages, or None when the address is not temp mail."""
    found = find_temp_mailbox(settings, email)
    if found is None:
        return None
    user_id, mailbox = found
    raw = read_temp_messages(settings, user_id, mailbox, temp_mail_providers)
    all_msgs = to_mailbox_messages(raw, mailbox.address)
    filtered = filter_messages(all_msgs, from_contains, subject_contains, since_minutes)
    total: int = len(filtered)
    paged: list[MailboxMessage] = filtered[skip : skip + top]
    return {
        "messages": [build_summary(m, i) for i, m in enumerate(paged)],
        "total": total,
        "has_more": (skip + top) < total,
    }


def temp_get_latest_message(
    settings: Settings,
    email: str,
    temp_mail_providers: dict[str, TempMailProvider],
    from_contains: str | None,
    subject_contains: str | None,
    since_minutes: int | None,
) -> dict[str, object] | None:
    found = find_temp_mailbox(settings, email)
    if found is None:
        return None
    user_id, mailbox = found
    raw = read_temp_messages(settings, user_id, mailbox, temp_mail_providers)
    all_msgs = to_mailbox_messages(raw, mailbox.address)
    filtered = filter_messages(all_msgs, from_contains, subject_contains, since_minutes)
    if not filtered:
        return {"found": False, "message": None}
    latest_index = _find_message_index(raw, filtered[0].message_id)
    return {
        "found": True,
        "message": build_summary(filtered[0], latest_index),
    }


def temp_get_message_detail(
    settings: Settings,
    email: str,
    temp_mail_providers: dict[str, TempMailProvider],
    message_id: str,
) -> dict[str, object] | None:
    found = find_temp_mailbox(settings, email)
    if found is None:
        return None
    user_id, mailbox = found
    raw = read_temp_messages(settings, user_id, mailbox, temp_mail_providers)
    index = _find_message_index(raw, message_id)
    if index < 0:
        return {"found": False, "message": None, "detail": "Message not found"}
    message = raw[index]
    return {
        "found": True,
        "message": {
            "id": message_id,
            "subject": message.subject,
            "from": message.from_address,
            "to": mailbox.address,
            "date": message.received_at,
            "body": f"{message.text}\n{message.html}".strip(),
            "body_type": "text",
        },
    }


def temp_get_message_raw(
    settings: Settings,
    email: str,
    temp_mail_providers: dict[str, TempMailProvider],
    message_id: str,
) -> dict[str, object] | None:
    found = find_temp_mailbox(settings, email)
    if found is None:
        return None
    user_id, mailbox = found
    raw = read_temp_messages(settings, user_id, mailbox, temp_mail_providers)
    index = _find_message_index(raw, message_id)
    if index < 0:
        return {"found": False, "raw": "", "detail": "Message not found"}
    message = raw[index]
    return {
        "found": True,
        "raw": f"{message.text}\n{message.html}".strip(),
        "subject": message.subject,
    }
