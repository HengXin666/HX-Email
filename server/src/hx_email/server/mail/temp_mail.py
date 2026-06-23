import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id
from hx_email.server.mail.email_accounts import DuplicateUsableEmailError


@dataclass(frozen=True)
class ProviderMailbox:
    provider_mailbox_id: str
    address: str


@dataclass(frozen=True)
class TempMailbox:
    id: int
    usable_email_id: int
    address: str
    label: str
    status: str
    provider: str
    provider_mailbox_id: str
    email_account_id: None = None


@dataclass(frozen=True)
class TempMailMessage:
    id: str
    from_address: str
    subject: str
    text: str
    html: str = ""


@dataclass(frozen=True)
class TempMailCode:
    message_id: str
    code: str


@dataclass(frozen=True)
class TempMailLink:
    message_id: str
    url: str


class TempMailMessageLike(Protocol):
    id: str
    from_address: str
    subject: str
    text: str
    html: str


class TempMailProvider(Protocol):
    def create_mailbox(
        self, requested_address: str | None = None
    ) -> ProviderMailbox | dict[str, str]: ...

    def list_messages(
        self, provider_mailbox_id: str
    ) -> list[TempMailMessage | Mapping[str, str] | TempMailMessageLike]: ...


class MissingTempMailProviderError(ValueError):
    pass


class TempMailboxNotFoundError(ValueError):
    pass


def provider_mailbox_from_result(result: ProviderMailbox | dict[str, str]) -> ProviderMailbox:
    if isinstance(result, ProviderMailbox):
        return result
    return ProviderMailbox(
        provider_mailbox_id=result["provider_mailbox_id"],
        address=result["address"],
    )


def message_from_result(
    result: TempMailMessage | Mapping[str, str] | TempMailMessageLike,
) -> TempMailMessage:
    if isinstance(result, TempMailMessage):
        return result
    if isinstance(result, Mapping):
        return TempMailMessage(
            id=result["id"],
            from_address=result["from_address"],
            subject=result["subject"],
            text=result["text"],
            html=result.get("html", ""),
        )
    return TempMailMessage(
        id=result.id,
        from_address=result.from_address,
        subject=result.subject,
        text=result.text,
        html=result.html,
    )


def create_cf_temp_mailbox(
    settings: Settings,
    user_id: int,
    provider: TempMailProvider,
    *,
    address: str | None,
    label: str,
) -> TempMailbox:
    provider_mailbox = provider_mailbox_from_result(provider.create_mailbox(address))
    label = label or provider_mailbox.address
    with connect(settings) as connection:
        try:
            email_cursor = connection.execute(
                """
                INSERT INTO usable_emails (
                    user_id, email_account_id, address, label, kind, status, active
                )
                VALUES (?, NULL, ?, ?, 'temp', 'active', 1)
                """,
                (user_id, provider_mailbox.address, label),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateUsableEmailError(
                "Usable email address already exists for this user"
            ) from error
        mailbox_cursor = connection.execute(
            """
            INSERT INTO temp_mailboxes (user_id, usable_email_id, provider, provider_mailbox_id)
            VALUES (?, ?, 'cf', ?)
            """,
            (user_id, email_cursor.lastrowid, provider_mailbox.provider_mailbox_id),
        )

    return TempMailbox(
        id=require_inserted_id(mailbox_cursor.lastrowid),
        usable_email_id=require_inserted_id(email_cursor.lastrowid),
        address=provider_mailbox.address,
        label=label,
        status="active",
        provider="cf",
        provider_mailbox_id=provider_mailbox.provider_mailbox_id,
    )


def get_temp_mailbox(settings: Settings, user_id: int, usable_email_id: int) -> TempMailbox | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT temp_mailboxes.id, temp_mailboxes.usable_email_id, usable_emails.address,
                   usable_emails.label, usable_emails.status, temp_mailboxes.provider,
                   temp_mailboxes.provider_mailbox_id
            FROM temp_mailboxes
            JOIN usable_emails
                ON usable_emails.id = temp_mailboxes.usable_email_id
                AND usable_emails.user_id = temp_mailboxes.user_id
            WHERE temp_mailboxes.user_id = ? AND temp_mailboxes.usable_email_id = ?
            """,
            (user_id, usable_email_id),
        ).fetchone()

    if row is None:
        return None
    return TempMailbox(
        id=row["id"],
        usable_email_id=row["usable_email_id"],
        address=row["address"],
        label=row["label"],
        status=row["status"],
        provider=row["provider"],
        provider_mailbox_id=row["provider_mailbox_id"],
    )


def archive_temp_mailbox(
    settings: Settings, user_id: int, usable_email_id: int
) -> TempMailbox | None:
    mailbox = get_temp_mailbox(settings, user_id, usable_email_id)
    if mailbox is None:
        return None
    with connect(settings) as connection:
        row = connection.execute(
            """
            UPDATE usable_emails
            SET status = 'archived', active = 1
            WHERE id = ? AND user_id = ? AND kind = 'temp'
            RETURNING id, address, label, status
            """,
            (usable_email_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return TempMailbox(
        id=mailbox.id,
        usable_email_id=row["id"],
        address=row["address"],
        label=row["label"],
        status=row["status"],
        provider=mailbox.provider,
        provider_mailbox_id=mailbox.provider_mailbox_id,
    )


def list_temp_messages(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    providers: dict[str, TempMailProvider],
) -> tuple[TempMailMessage, ...]:
    mailbox = get_temp_mailbox(settings, user_id, usable_email_id)
    if mailbox is None:
        raise TempMailboxNotFoundError("Temp mailbox not found")
    provider = providers.get(mailbox.provider)
    if provider is None:
        raise MissingTempMailProviderError(
            f"Temp mail provider is not configured: {mailbox.provider}"
        )
    return tuple(
        message_from_result(message)
        for message in provider.list_messages(mailbox.provider_mailbox_id)
    )


def extract_codes(messages: tuple[TempMailMessage, ...]) -> tuple[TempMailCode, ...]:
    codes: list[TempMailCode] = []
    seen: set[tuple[str, str]] = set()
    for message in messages:
        content = f"{message.subject}\n{message.text}\n{message.html}"
        for match in re.finditer(r"(?<!\d)(\d{4,8})(?!\d)", content):
            key = (message.id, match.group(1))
            if key not in seen:
                seen.add(key)
                codes.append(TempMailCode(message_id=message.id, code=match.group(1)))
    return tuple(codes)


def extract_links(messages: tuple[TempMailMessage, ...]) -> tuple[TempMailLink, ...]:
    links: list[TempMailLink] = []
    for message in messages:
        content = f"{message.text}\n{message.html}"
        for match in re.finditer(r"https?://[^\s\"'<>)]+", content):
            links.append(TempMailLink(message_id=message.id, url=match.group(0)))
    return tuple(links)
