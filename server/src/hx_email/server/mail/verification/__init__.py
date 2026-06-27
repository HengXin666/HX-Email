"""Verification code reading — public API."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.imap.message_store import get_messages
from hx_email.server.mail.usable_emails import UsableEmail
from hx_email.server.mail.verification.db import load_target, load_usable_email
from hx_email.server.mail.verification.extract import (
    CODE_PATTERN,
    LINK_PATTERN,
    extract_verification_code,
    first_match,
)

__all__ = [
    "CODE_PATTERN",
    "LINK_PATTERN",
    "EmptyMailboxProvider",
    "FolderMailboxProvider",
    "MailboxProvider",
    "VerificationMatch",
    "VerificationReading",
    "VerificationState",
    "coerce_message",
    "extract_verification_code",
    "first_match",
    "get_verification_history",
    "get_verification_state",
    "load_target",
    "load_usable_email",
    "read_verification",
    "save_history",
]


@dataclass(frozen=True)
class VerificationMatch:
    code: str | None
    link: str | None
    recipient_address: str | None
    certainty: str
    subject: str


@dataclass(frozen=True)
class VerificationReading:
    usable_email: UsableEmail
    matches: tuple[VerificationMatch, ...]


@dataclass(frozen=True)
class VerificationState:
    last_extracted_at: str | None
    seen_codes: frozenset[str]


class MailboxProvider(Protocol):
    def read_messages(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
    ) -> list[MailboxMessage | dict[str, object]]: ...


@runtime_checkable
class FolderMailboxProvider(Protocol):
    def read_messages_folder(
        self,
        email_account: EmailAccountMailbox,
        *,
        folder: str,
        top: int,
        skip: int = 0,
    ) -> list[MailboxMessage | dict[str, object]]: ...


class EmptyMailboxProvider:
    def read_messages(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
    ) -> list[MailboxMessage]:
        return []


def read_verification(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    mailbox_provider: MailboxProvider,
    force_refresh: bool = False,
) -> VerificationReading | None:
    target = load_target(settings, user_id, usable_email_id)
    if target is None:
        return None
    usable_email, email_account = target
    matches: list[VerificationMatch] = []
    cached_msgs: list[dict[str, object]] = []
    if not force_refresh:
        cached_msgs = get_messages(settings, usable_email_id)
    for msg in cached_msgs:
        rcp: str | None = str(msg["recipient_address"]) if msg.get("recipient_address") else None
        if rcp and rcp.lower() != usable_email.address.lower():
            continue
        subj: str = str(msg.get("subject") or "")
        content = f"{subj}\n{msg.get('body') or ''!s}"
        code = extract_verification_code(content)
        if code is None:
            continue
        matches.append(
            VerificationMatch(
                code=code,
                link=None,
                recipient_address=rcp,
                certainty="certain" if rcp else "uncertain",
                subject=subj,
            )
        )
    should_fetch_live = force_refresh or not cached_msgs
    if should_fetch_live and not matches:
        try:
            for raw_message in mailbox_provider.read_messages(email_account):
                message = coerce_message(raw_message)
                if (
                    message.recipient_address is not None
                    and message.recipient_address.lower() != usable_email.address.lower()
                ):
                    continue
                content = f"{message.subject}\n{message.body}"
                code = extract_verification_code(content)
                if code is None:
                    continue
                matches.append(
                    VerificationMatch(
                        code=code,
                        link=None,
                        recipient_address=message.recipient_address,
                        certainty="certain"
                        if message.recipient_address is not None
                        else "uncertain",
                        subject=message.subject,
                    )
                )
        except Exception:
            pass
    reading = VerificationReading(usable_email=usable_email, matches=tuple(matches))
    save_history(settings, user_id, usable_email.id, reading.matches)
    return reading


def get_verification_state(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> VerificationState:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT code, created_at FROM verification_readings "
            "WHERE user_id = ? AND usable_email_id = ? ORDER BY id",
            (user_id, usable_email_id),
        ).fetchall()
    if not rows:
        return VerificationState(last_extracted_at=None, seen_codes=frozenset())
    codes = frozenset(r["code"] for r in rows if r["code"])
    return VerificationState(last_extracted_at=rows[-1]["created_at"], seen_codes=codes)


def get_verification_history(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> VerificationReading | None:
    target = load_usable_email(settings, user_id, usable_email_id)
    if target is None:
        return None
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT code, link, recipient_address, certainty, subject "
            "FROM verification_readings "
            "WHERE user_id = ? AND usable_email_id = ? ORDER BY id",
            (user_id, usable_email_id),
        ).fetchall()
    return VerificationReading(
        usable_email=target,
        matches=tuple(
            VerificationMatch(
                code=r["code"],
                link=r["link"],
                recipient_address=r["recipient_address"],
                certainty=r["certainty"],
                subject=r["subject"],
            )
            for r in rows
        ),
    )


def save_history(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    matches: tuple[VerificationMatch, ...],
) -> None:
    if not matches:
        return
    with connect(settings) as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO verification_readings "
            "(user_id, usable_email_id, code, link, recipient_address, "
            "certainty, subject) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    user_id,
                    usable_email_id,
                    m.code,
                    m.link,
                    m.recipient_address,
                    m.certainty,
                    m.subject,
                )
                for m in matches
            ],
        )


def coerce_message(message: MailboxMessage | dict[str, object]) -> MailboxMessage:
    if isinstance(message, MailboxMessage):
        return message
    rcp = message.get("recipient_address")
    return MailboxMessage(
        recipient_address=rcp if isinstance(rcp, str) else None,
        subject=str(message.get("subject", "")),
        body=str(message.get("body", "")),
    )
