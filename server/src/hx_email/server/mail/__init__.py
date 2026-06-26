from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailAccountMailbox:
    id: int
    provider: str
    primary_address: str


@dataclass(frozen=True)
class MailboxMessage:
    recipient_address: str | None
    subject: str
    body: str
    from_address: str = ""
    received_at: str = ""
    message_id: str = ""
