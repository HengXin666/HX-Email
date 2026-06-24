"""Temp mail service: message operations (detail, delete, clear, refresh, mailbox delete)."""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.temp_mail import (
    TempMailMessage,
    TempMailProvider,
    get_temp_mailbox,
    list_temp_messages,
)


def get_temp_message_detail(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    temp_mail_providers: dict[str, TempMailProvider],
    message_id: str,
) -> dict[str, object] | None:
    """Get a single temp mail message with full body text and html.

    Fetches all messages from the provider and filters by message_id.
    """
    messages = list_temp_messages(settings, user_id, usable_email_id, temp_mail_providers)
    return _find_message(messages, message_id)


def _find_message(
    messages: tuple[TempMailMessage, ...],
    message_id: str,
) -> dict[str, object] | None:
    for message in messages:
        if message.id == message_id:
            return {
                "id": message.id,
                "from_address": message.from_address,
                "subject": message.subject,
                "text": message.text,
                "html": message.html,
            }
    return None


def delete_temp_message(
    settings: Settings,
    usable_email_id: int,
    message_id: str,
) -> None:
    """Mark a temp mail message as deleted.

    Since messages come from the remote provider and are not stored locally,
    this is a no-op acknowledgement. The provider may not support
    individual message deletion.
    """
    # Provider protocol does not expose a delete_message method.
    # Future enhancement: maintain a local deleted-message-id registry.


def delete_temp_mailbox(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> bool:
    """Permanently delete a temp mailbox and its usable email record.

    Returns True if deletion succeeded, False if not found.
    """
    mailbox = get_temp_mailbox(settings, user_id, usable_email_id)
    if mailbox is None:
        return False
    with connect(settings) as connection:
        connection.execute(
            "DELETE FROM temp_mailboxes WHERE user_id = ? AND usable_email_id = ?",
            (user_id, usable_email_id),
        )
        connection.execute(
            "DELETE FROM usable_emails WHERE id = ? AND user_id = ? AND kind = 'temp'",
            (usable_email_id, user_id),
        )
    return True


def clear_temp_messages(
    settings: Settings,
    usable_email_id: int,
) -> None:
    """Clear all messages for a temp mail mailbox.

    Since messages come from the remote provider and are not stored locally,
    this is a no-op acknowledgement.
    """
    # Provider protocol does not expose a clear_messages method.


def refresh_temp_mail(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    temp_mail_providers: dict[str, TempMailProvider],
) -> dict[str, object]:
    """Trigger a remote fetch for new messages and return them."""
    messages = list_temp_messages(settings, user_id, usable_email_id, temp_mail_providers)
    return {
        "messages": [
            {
                "id": message.id,
                "from_address": message.from_address,
                "subject": message.subject,
                "text": message.text,
                "html": message.html,
            }
            for message in messages
        ],
        "total": len(messages),
    }
