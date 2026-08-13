"""External verification extraction: real mailboxes with temp-mail fallback."""

from __future__ import annotations

from typing import Any

from hx_email.config import Settings
from hx_email.server.external_api.impl.mail.helpers import (
    coerce_messages,
    filter_messages,
    resolve_email,
)
from hx_email.server.external_api.impl.mail.temp_mail_reader import (
    _find_message_index,
    find_temp_mailbox,
    read_temp_messages,
    to_mailbox_messages,
)
from hx_email.server.mail import MailboxMessage
from hx_email.server.mail.impl.email_service import _find_email_account
from hx_email.server.mail.temp_mail import TempMailProvider
from hx_email.server.mail.verification import (
    LINK_PATTERN,
    DeliveryTarget,
    MailboxProvider,
    find_verification_code,
    first_match,
)


def extract_verification_code(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email: str,
    folder: str = "inbox",
    from_contains: str | None = None,
    subject_contains: str | None = None,
    since_minutes: int | None = None,
    code_length: int | None = None,
    code_regex: str | None = None,
    code_source: str = "all",
    claim_token: str | None = None,
    temp_mail_providers: dict[str, TempMailProvider] | None = None,
) -> dict[str, object]:
    """Extract verification code from messages.

    When no custom regex or length is given, uses keyword-context-aware
    extraction that only matches codes near verification keywords.
    """
    resolved_email = resolve_email(settings, email, claim_token)
    account = _find_email_account(settings, resolved_email)
    if account is None:
        if temp_mail_providers:
            temp_result = temp_extract_verification_code(
                settings,
                resolved_email,
                temp_mail_providers,
                from_contains,
                subject_contains,
                since_minutes,
                code_length,
                code_regex,
                code_source,
            )
            if temp_result is not None:
                return temp_result
        return {"verification_code": "", "matched_email_id": "", "match_count": 0}

    raw_all: list[Any] = mailbox_provider.read_messages(account)
    all_msgs: list[MailboxMessage] = coerce_messages(raw_all)
    filtered: list[MailboxMessage] = filter_messages(
        all_msgs, from_contains, subject_contains, since_minutes
    )
    return find_verification_code(
        filtered,
        DeliveryTarget(address=resolved_email, provider=account.provider),
        code_length=code_length,
        code_regex=code_regex,
        code_source=code_source,
    )


def extract_verification_link(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email: str,
    folder: str = "inbox",
    from_contains: str | None = None,
    subject_contains: str | None = None,
    since_minutes: int | None = None,
    claim_token: str | None = None,
    temp_mail_providers: dict[str, TempMailProvider] | None = None,
) -> dict[str, object]:
    """Extract verification link from messages."""
    resolved_email = resolve_email(settings, email, claim_token)
    account = _find_email_account(settings, resolved_email)
    if account is None:
        if temp_mail_providers:
            temp_result = temp_extract_verification_link(
                settings,
                resolved_email,
                temp_mail_providers,
                from_contains,
                subject_contains,
                since_minutes,
            )
            if temp_result is not None:
                return temp_result
        return {"verification_link": "", "matched_email_id": "", "match_count": 0}

    raw_all: list[Any] = mailbox_provider.read_messages(account)
    all_msgs: list[MailboxMessage] = coerce_messages(raw_all)
    filtered: list[MailboxMessage] = filter_messages(
        all_msgs, from_contains, subject_contains, since_minutes
    )

    for idx, msg in enumerate(filtered):
        content = f"{msg.subject}\n{msg.body or ''}"
        link = first_match(LINK_PATTERN, content)
        if link is not None:
            return {
                "verification_link": link,
                "matched_email_id": str(idx + 1),
                "matched_subject": msg.subject,
                "match_count": 1,
            }

    return {"verification_link": "", "matched_email_id": "", "match_count": 0}


def temp_extract_verification_code(
    settings: Settings,
    email: str,
    temp_mail_providers: dict[str, TempMailProvider],
    from_contains: str | None,
    subject_contains: str | None,
    since_minutes: int | None,
    code_length: int | None,
    code_regex: str | None,
    code_source: str,
) -> dict[str, object] | None:
    found = find_temp_mailbox(settings, email)
    if found is None:
        return None
    user_id, mailbox = found
    raw = read_temp_messages(settings, user_id, mailbox, temp_mail_providers)
    all_msgs = to_mailbox_messages(raw, mailbox.address)
    filtered = filter_messages(all_msgs, from_contains, subject_contains, since_minutes)
    return find_verification_code(
        filtered,
        DeliveryTarget(address=mailbox.address, provider="cf"),
        code_length=code_length,
        code_regex=code_regex,
        code_source=code_source,
    )


def temp_extract_verification_link(
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
    for msg in filtered:
        content = f"{msg.subject}\n{msg.body or ''}"
        link = first_match(LINK_PATTERN, content)
        if link is not None:
            return {
                "verification_link": link,
                "matched_email_id": str(_find_message_index(raw, msg.message_id) + 1),
                "matched_subject": msg.subject,
                "match_count": 1,
            }
    return {"verification_link": "", "matched_email_id": "", "match_count": 0}
