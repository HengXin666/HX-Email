import re
from dataclasses import dataclass
from typing import Protocol

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.imap.message_store import get_messages
from hx_email.server.mail.usable_emails import UsableEmail

CODE_PATTERN = re.compile(r"\b\d{6}\b")
LINK_PATTERN = re.compile(r"https?://[^\s]+")


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
    force_refresh: bool = False,
) -> VerificationReading | None:
    target = load_target(settings, user_id, usable_email_id)
    if target is None:
        return None
    usable_email, email_account = target
    matches: list[VerificationMatch] = []
    cached_msgs: list[dict[str, object]] = []
    # Always try cache first (unless force_refresh)
    if not force_refresh:
        cached_msgs = get_messages(settings, usable_email_id)
    for msg in cached_msgs:
        recipient: str | None = (
            str(msg["recipient_address"]) if msg.get("recipient_address") else None
        )
        if recipient and recipient.lower() != usable_email.address.lower():
            continue
        subject: str = str(msg.get("subject") or "")
        body: str = str(msg.get("body") or "")
        content = f"{subject}\n{body}"
        code = first_match(CODE_PATTERN, content)
        link = first_match(LINK_PATTERN, content)
        if code is None and link is None:
            continue
        matches.append(
            VerificationMatch(
                code=code,
                link=link,
                recipient_address=recipient,
                certainty="certain" if recipient else "uncertain",
                subject=subject,
            )
        )
    # Only hit live IMAP when explicitly forced, or when cache is truly empty.
    # Having cached messages without codes is normal — don't retry IMAP.
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
                code = first_match(CODE_PATTERN, content)
                link = first_match(LINK_PATTERN, content)
                if code is None and link is None:
                    continue
                matches.append(
                    VerificationMatch(
                        code=code,
                        link=link,
                        recipient_address=message.recipient_address,
                        certainty=(
                            "certain" if message.recipient_address is not None else "uncertain"
                        ),
                        subject=message.subject,
                    )
                )
        except Exception:
            # IMAP may be unreachable; return whatever cache gave us.
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
            """
            SELECT code, created_at
            FROM verification_readings
            WHERE user_id = ? AND usable_email_id = ?
            ORDER BY id
            """,
            (user_id, usable_email_id),
        ).fetchall()
    if not rows:
        return VerificationState(last_extracted_at=None, seen_codes=frozenset())
    codes = frozenset(r["code"] for r in rows if r["code"])
    last_at = rows[-1]["created_at"]
    return VerificationState(last_extracted_at=last_at, seen_codes=codes)


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
