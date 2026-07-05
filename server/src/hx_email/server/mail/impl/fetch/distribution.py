from __future__ import annotations

from hx_email.config import Settings
from hx_email.server.mail import MailboxMessage
from hx_email.server.mail.imap.message_store import save_messages
from hx_email.server.mail.impl.fetch.targets import FetchUsableEmail
from hx_email.server.mail.verification import (
    DeliveryTarget,
    VerificationMatch,
    extract_verification_code,
    message_matches_target,
    save_history,
)


def store_messages_for_usable_emails(
    settings: Settings,
    user_id: int,
    account_id: int,
    email_rows: list[FetchUsableEmail],
    messages: list[MailboxMessage],
) -> tuple[int, int]:
    addressed: list[MailboxMessage] = []
    broadcast: list[MailboxMessage] = []
    for message in messages:
        if message.recipient_address is None:
            broadcast.append(message)
        else:
            addressed.append(message)

    total_stored: int = 0
    codes_found: int = 0
    primary_row = email_rows[0] if email_rows else None
    matched_message_ids: set[int] = set()

    if primary_row and broadcast:
        total_stored += save_messages(settings, user_id, primary_row.id, account_id, broadcast)
        codes_found += save_codes(settings, user_id, primary_row.id, broadcast, certainty="medium")

    for email_row in email_rows:
        target = DeliveryTarget(
            address=email_row.address,
            provider=email_row.provider,
            kind=email_row.kind,
        )
        relevant = [
            message
            for message in addressed
            if message_matches_target(target, message.recipient_address)
        ]
        if not relevant:
            continue
        matched_message_ids.update(id(message) for message in relevant)
        total_stored += save_messages(settings, user_id, email_row.id, account_id, relevant)
        codes_found += save_codes(settings, user_id, email_row.id, relevant, certainty="high")

    if primary_row:
        unmatched = [message for message in addressed if id(message) not in matched_message_ids]
        total_stored += save_messages(settings, user_id, primary_row.id, account_id, unmatched)

    return total_stored, codes_found


def save_codes(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    messages: list[MailboxMessage],
    *,
    certainty: str,
) -> int:
    codes_found: int = 0
    for message in messages:
        code = extract_verification_code(f"{message.subject}\n{message.body}")
        if not code:
            continue
        match = VerificationMatch(
            code=code,
            link=None,
            recipient_address=message.recipient_address,
            certainty=certainty,
            subject=message.subject,
        )
        save_history(settings, user_id, usable_email_id, (match,))
        codes_found += 1
    return codes_found
