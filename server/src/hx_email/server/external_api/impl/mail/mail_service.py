"""External mail service: message operations for external API consumers."""

from __future__ import annotations

from typing import Any

from hx_email.config import Settings
from hx_email.server.external_api.impl.mail.helpers import (
    build_summary,
    coerce_messages,
    filter_messages,
    resolve_email,
)
from hx_email.server.mail import MailboxMessage
from hx_email.server.mail.impl.email_service import _find_email_account
from hx_email.server.mail.verification import (
    LINK_PATTERN,
    DeliveryTarget,
    MailboxProvider,
    coerce_message,
    find_verification_code,
    first_match,
)


def get_messages(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
    from_contains: str | None = None,
    subject_contains: str | None = None,
    since_minutes: int | None = None,
    claim_token: str | None = None,
) -> dict[str, object]:
    """Fetch messages with optional filters. If claim_token, resolve email from pool claim."""
    resolved_email: str = resolve_email(settings, email, claim_token)
    account = _find_email_account(settings, resolved_email)
    if account is None:
        return {"messages": [], "total": 0, "has_more": False}

    raw_all: list[Any] = mailbox_provider.read_messages(account)
    all_msgs: list[MailboxMessage] = coerce_messages(raw_all)
    filtered: list[MailboxMessage] = filter_messages(
        all_msgs, from_contains, subject_contains, since_minutes
    )

    total: int = len(filtered)
    paged: list[MailboxMessage] = filtered[skip : skip + top]
    has_more: bool = (skip + top) < total

    return {
        "messages": [build_summary(m, i) for i, m in enumerate(paged)],
        "total": total,
        "has_more": has_more,
    }


def get_latest_message(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email: str,
    folder: str = "inbox",
    from_contains: str | None = None,
    subject_contains: str | None = None,
    since_minutes: int | None = None,
    claim_token: str | None = None,
) -> dict[str, object]:
    """Get single latest message matching filters."""
    resolved_email = resolve_email(settings, email, claim_token)
    account = _find_email_account(settings, resolved_email)
    if account is None:
        return {"found": False, "message": None}

    raw_all: list[Any] = mailbox_provider.read_messages(account)
    all_msgs: list[MailboxMessage] = coerce_messages(raw_all)
    filtered: list[MailboxMessage] = filter_messages(
        all_msgs, from_contains, subject_contains, since_minutes
    )

    if not filtered:
        return {"found": False, "message": None}

    latest: MailboxMessage = filtered[-1]
    return {
        "found": True,
        "message": build_summary(latest, len(all_msgs) - 1),
    }


def get_message_detail(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email: str,
    message_id: str,
    folder: str = "inbox",
    claim_token: str | None = None,
) -> dict[str, object]:
    """Get full message detail with body."""
    resolved_email = resolve_email(settings, email, claim_token)
    account = _find_email_account(settings, resolved_email)
    if account is None:
        return {"found": False, "message": None, "detail": "Account not found"}

    raw_all: list[Any] = mailbox_provider.read_messages(account)
    try:
        idx: int = int(message_id) - 1
        if idx < 0 or idx >= len(raw_all):
            return {"found": False, "message": None, "detail": "Message not found"}
        msg: MailboxMessage = coerce_message(raw_all[idx])
        return {
            "found": True,
            "message": {
                "id": message_id,
                "subject": msg.subject,
                "from": "",
                "to": resolved_email,
                "date": "",
                "body": msg.body or "",
                "body_type": "text",
            },
        }
    except (ValueError, IndexError):
        return {"found": False, "message": None, "detail": "Invalid message ID"}


def get_message_raw(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email: str,
    message_id: str,
    folder: str = "inbox",
    claim_token: str | None = None,
) -> dict[str, object]:
    """Get raw MIME content of a message.

    Since the provider does not expose raw MIME, returns the body as text.
    """
    resolved_email = resolve_email(settings, email, claim_token)
    account = _find_email_account(settings, resolved_email)
    if account is None:
        return {"found": False, "raw": "", "detail": "Account not found"}

    raw_all: list[Any] = mailbox_provider.read_messages(account)
    try:
        idx = int(message_id) - 1
        if idx < 0 or idx >= len(raw_all):
            return {"found": False, "raw": "", "detail": "Message not found"}
        msg = coerce_message(raw_all[idx])
        return {
            "found": True,
            "raw": msg.body or "",
            "subject": msg.subject,
        }
    except (ValueError, IndexError):
        return {"found": False, "raw": "", "detail": "Invalid message ID"}


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
) -> dict[str, object]:
    """Extract verification code from messages.

    When no custom regex or length is given, uses keyword-context-aware
    extraction that only matches codes near verification keywords.
    """
    resolved_email = resolve_email(settings, email, claim_token)
    account = _find_email_account(settings, resolved_email)
    if account is None:
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
) -> dict[str, object]:
    """Extract verification link from messages."""
    resolved_email = resolve_email(settings, email, claim_token)
    account = _find_email_account(settings, resolved_email)
    if account is None:
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
