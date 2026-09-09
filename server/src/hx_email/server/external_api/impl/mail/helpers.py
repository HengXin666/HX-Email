"""Shared helpers for external mail services."""

from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.verification import (
    FolderMailboxProvider,
    MailboxProvider,
    coerce_message,
)

# Simple in-memory probe store: {probe_id: {status, result, created_at}}
_probes: dict[str, dict[str, object]] = {}


def resolve_email_from_claim(
    settings: Settings,
    claim_token: str | None,
    email: str,
) -> str:
    """Resolve email from pool claim token if provided, otherwise return email."""
    if not claim_token:
        return email
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT ue.address
            FROM mail_pool_entries mpe
            JOIN usable_emails ue ON ue.id = mpe.usable_email_id
            WHERE mpe.claim_key = ? AND mpe.status = 'claimed'
            """,
            (claim_token,),
        ).fetchone()
        if row is not None:
            return str(row["address"])
    return email


def resolve_email(settings: Settings, email: str, claim_token: str | None = None) -> str:
    """Resolve email, optionally from claim token."""
    return resolve_email_from_claim(settings, claim_token, email)


def coerce_messages(raw_messages: list[Any]) -> list[MailboxMessage]:
    """Convert raw messages to MailboxMessage list."""
    return [coerce_message(raw) for raw in raw_messages]


def read_messages_with_junk(
    mailbox_provider: MailboxProvider,
    account: EmailAccountMailbox,
    folder: str = "inbox",
    top: int = 50,
) -> list[MailboxMessage]:
    """读指定文件夹 + 垃圾邮件箱 (验证码常被判垃圾), 按 message_id/主题/时间去重。"""
    if isinstance(mailbox_provider, FolderMailboxProvider):
        raw: list[Any] = []
        for target in (folder, "junk"):
            try:
                raw.extend(mailbox_provider.read_messages_folder(account, folder=target, top=top))
            except Exception:
                continue
        return dedupe_messages(coerce_messages(raw))
    return coerce_messages(list(mailbox_provider.read_messages(account)))


def dedupe_messages(messages: list[MailboxMessage]) -> list[MailboxMessage]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[MailboxMessage] = []
    for message in messages:
        key = (message.message_id, message.subject, message.received_at)
        if key in seen:
            continue
        seen.add(key)
        unique.append(message)
    return unique


def filter_messages(
    messages: list[MailboxMessage],
    from_contains: str | None,
    subject_contains: str | None,
    since_minutes: int | None,
) -> list[MailboxMessage]:
    """Filter messages by optional criteria."""
    filtered: list[MailboxMessage] = list(messages)
    if from_contains:
        f_lower = from_contains.lower()
        filtered = [
            m for m in filtered if f_lower in m.subject.lower() or f_lower in (m.body or "").lower()
        ]
    if subject_contains:
        s_lower = subject_contains.lower()
        filtered = [m for m in filtered if s_lower in m.subject.lower()]
    if since_minutes is not None and since_minutes > 0:
        pass  # Timestamps not available from MailboxMessage; skip time filter
    return filtered


def build_summary(msg: MailboxMessage, idx: int) -> dict[str, object]:
    """Build a message summary dict."""
    return {
        "id": str(idx + 1),
        "subject": msg.subject,
        "from": "",
        "to": msg.recipient_address or "",
        "date": "",
        "body_preview": (msg.body or "")[:200],
        "has_attachments": False,
    }
