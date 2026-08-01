"""Typed contracts shared by delivery orchestration and channel adapters."""

from dataclasses import dataclass
from typing import Literal

DeliveryChannel = Literal["email", "telegram", "webhook", "script"]


@dataclass(frozen=True)
class DeliveryConfig:
    email_enabled: bool
    telegram_enabled: bool
    webhook_enabled: bool
    script_enabled: bool


@dataclass(frozen=True)
class StoredMessageEvent:
    id: int
    user_id: int
    usable_email_id: int
    email_account_id: int | None
    address: str
    group_id: int | None
    group_name: str
    email_notify_enabled: bool
    group_notify_enabled: bool
    account_telegram_enabled: bool
    from_address: str
    recipient_address: str
    subject: str
    body: str
    received_at: str


@dataclass(frozen=True)
class DeliveryJob:
    id: int
    fetched_message_id: int
    channel: DeliveryChannel
    attempts: int


@dataclass(frozen=True)
class DispatchSummary:
    queued: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "queued": self.queued,
            "sent": self.sent,
            "failed": self.failed,
            "skipped": self.skipped,
        }
