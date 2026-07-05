"""Search mailbox messages for verification artifacts for one delivery target."""

from __future__ import annotations

import re

from hx_email.server.mail import MailboxMessage
from hx_email.server.mail.verification.addresses import DeliveryTarget, message_matches_target
from hx_email.server.mail.verification.extract import (
    CODE_PATTERN,
    extract_verification_code,
    first_match,
)


def find_verification_code(
    messages: list[MailboxMessage],
    target: DeliveryTarget,
    *,
    code_length: int | None = None,
    code_regex: str | None = None,
    code_source: str = "all",
) -> dict[str, object]:
    """Return the first code from messages addressed to the requested usable email."""
    pattern: re.Pattern[str] | None = None
    if code_regex or code_length is not None:
        pattern = re.compile(code_regex) if code_regex else CODE_PATTERN

    for idx, message in enumerate(messages):
        if not message_matches_target(target, message.recipient_address):
            continue
        content: str = message_content_for_source(message, code_source)
        code: str | None = (
            first_match(pattern, content)
            if pattern is not None
            else extract_verification_code(content)
        )
        if code is not None:
            return {
                "verification_code": code,
                "matched_email_id": str(idx + 1),
                "matched_subject": message.subject,
                "match_count": 1,
            }

    return {"verification_code": "", "matched_email_id": "", "match_count": 0}


def message_content_for_source(message: MailboxMessage, code_source: str) -> str:
    if code_source == "subject":
        return message.subject
    if code_source == "body":
        return message.body or ""
    return f"{message.subject}\n{message.body or ''}"
