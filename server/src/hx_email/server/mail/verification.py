import re
from dataclasses import dataclass
from typing import Protocol

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.usable_emails import UsableEmail

CODE_PATTERN = re.compile(r"\b\d{6}\b")
LINK_PATTERN = re.compile(r"https?://[^\s]+")


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


class MailboxProvider(Protocol):
    def read_messages(
        self, email_account: EmailAccountMailbox
    ) -> list[MailboxMessage | dict[str, object]]: ...


class EmptyMailboxProvider:
    def read_messages(self, email_account: EmailAccountMailbox) -> list[MailboxMessage]:
        return []


def read_verification(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    mailbox_provider: MailboxProvider,
) -> VerificationReading | None:
    target = load_target(settings, user_id, usable_email_id)
    if target is None:
        return None

    usable_email, email_account = target
    matches: list[VerificationMatch] = []
    for raw_message in mailbox_provider.read_messages(email_account):
        message = coerce_message(raw_message)
        if (
            message.recipient_address is not None
            and message.recipient_address.lower() != usable_email.address.lower()
        ):
            continue

        content = f"{message.subject}\n{message.body}"
        code = first_match(CODE_PATTERN, content)
        link = first_match(LINK_PATTERN, content)
        if code is None and link is None:
            continue

        matches.append(
            VerificationMatch(
                code=code,
                link=link,
                recipient_address=message.recipient_address,
                certainty="certain" if message.recipient_address is not None else "uncertain",
                subject=message.subject,
            )
        )

    reading = VerificationReading(usable_email=usable_email, matches=tuple(matches))
    save_history(settings, user_id, usable_email.id, reading.matches)
    return reading


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
            """
            SELECT code, link, recipient_address, certainty, subject
            FROM verification_readings
            WHERE user_id = ? AND usable_email_id = ?
            ORDER BY id
            """,
            (user_id, usable_email_id),
        ).fetchall()

    return VerificationReading(
        usable_email=target,
        matches=tuple(
            VerificationMatch(
                code=row["code"],
                link=row["link"],
                recipient_address=row["recipient_address"],
                certainty=row["certainty"],
                subject=row["subject"],
            )
            for row in rows
        ),
    )


def load_target(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> tuple[UsableEmail, EmailAccountMailbox] | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT usable_emails.id AS usable_email_id,
                   usable_emails.address,
                   usable_emails.label,
                   usable_emails.kind,
                   usable_emails.status,
                   email_accounts.id AS email_account_id,
                   email_accounts.provider,
                   email_accounts.primary_address
            FROM usable_emails
            JOIN email_accounts ON email_accounts.id = usable_emails.email_account_id
                 AND email_accounts.user_id = usable_emails.user_id
            WHERE usable_emails.id = ? AND usable_emails.user_id = ?
            """,
            (usable_email_id, user_id),
        ).fetchone()

    if row is None:
        return None

    usable_email = UsableEmail(
        id=row["usable_email_id"],
        address=row["address"],
        label=row["label"],
        kind=row["kind"],
        status=row["status"],
    )
    email_account = EmailAccountMailbox(
        id=row["email_account_id"],
        provider=row["provider"],
        primary_address=row["primary_address"],
    )
    return usable_email, email_account


def load_usable_email(settings: Settings, user_id: int, usable_email_id: int) -> UsableEmail | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id, address, label, kind, status
            FROM usable_emails
            WHERE id = ? AND user_id = ?
            """,
            (usable_email_id, user_id),
        ).fetchone()

    if row is None:
        return None

    return UsableEmail(
        id=row["id"],
        address=row["address"],
        label=row["label"],
        kind=row["kind"],
        status=row["status"],
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
            """
            INSERT INTO verification_readings (
                user_id, usable_email_id, code, link, recipient_address, certainty, subject
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    user_id,
                    usable_email_id,
                    match.code,
                    match.link,
                    match.recipient_address,
                    match.certainty,
                    match.subject,
                )
                for match in matches
            ],
        )


def coerce_message(message: MailboxMessage | dict[str, object]) -> MailboxMessage:
    if isinstance(message, MailboxMessage):
        return message

    recipient_address = message.get("recipient_address")
    return MailboxMessage(
        recipient_address=recipient_address if isinstance(recipient_address, str) else None,
        subject=str(message.get("subject", "")),
        body=str(message.get("body", "")),
    )


def first_match(pattern: re.Pattern[str], content: str) -> str | None:
    match = pattern.search(content)
    return match.group(0) if match else None
