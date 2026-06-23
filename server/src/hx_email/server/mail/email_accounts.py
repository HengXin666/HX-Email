import sqlite3
from dataclasses import dataclass
from sqlite3 import Connection, Row

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id
from hx_email.server.mail.usable_emails import UsableEmail


@dataclass(frozen=True)
class EmailAccount:
    id: int
    provider: str
    primary_address: str
    display_name: str
    status: str
    primary_usable_email: UsableEmail
    usable_emails: tuple[UsableEmail, ...] = ()


class DuplicateUsableEmailError(ValueError):
    pass


class InvalidAliasAddressError(ValueError):
    pass


def is_plus_subaddress(address: str) -> bool:
    local_part, separator, _domain = address.partition("@")
    return bool(separator) and "+" in local_part


def usable_email_from_row(row: Row) -> UsableEmail:
    return UsableEmail(
        id=row["id"],
        address=row["address"],
        label=row["label"],
        kind=row["kind"],
        status=row["status"],
    )


def add_alias_email(
    connection: Connection,
    user_id: int,
    account_id: int,
    address: str,
    label: str,
) -> UsableEmail:
    if is_plus_subaddress(address):
        raise InvalidAliasAddressError("Alias address must be a real mailbox address")

    try:
        cursor = connection.execute(
            """
            INSERT INTO usable_emails (
                user_id, email_account_id, address, label, kind, status, active
            )
            VALUES (?, ?, ?, ?, 'alias', 'active', 1)
            """,
            (user_id, account_id, address, label),
        )
    except sqlite3.IntegrityError as error:
        raise DuplicateUsableEmailError(
            "Usable email address already exists for this user"
        ) from error

    return UsableEmail(
        id=require_inserted_id(cursor.lastrowid),
        address=address,
        label=label,
        kind="alias",
        status="active",
    )


def add_email_account(
    settings: Settings,
    user_id: int,
    provider: str,
    primary_address: str,
    display_name: str,
    imap_host: str = "",
    imap_port: int | None = None,
    username: str = "",
    alias_addresses: list[str] | None = None,
) -> EmailAccount:
    alias_addresses = alias_addresses or []
    with connect(settings) as connection:
        try:
            account_cursor = connection.execute(
                """
                INSERT INTO email_accounts (
                    user_id, provider, primary_address, display_name, imap_host,
                    imap_port, username
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, provider, primary_address, display_name, imap_host, imap_port, username),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateUsableEmailError(
                "Email account primary address already exists for this user"
            ) from error
        account_id = require_inserted_id(account_cursor.lastrowid)
        try:
            email_cursor = connection.execute(
                """
                INSERT INTO usable_emails (
                    user_id, email_account_id, address, label, kind, status, active
                )
                VALUES (?, ?, ?, ?, 'primary', 'active', 1)
                """,
                (user_id, account_id, primary_address, display_name),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateUsableEmailError(
                "Usable email address already exists for this user"
            ) from error
        alias_emails = [
            add_alias_email(connection, user_id, account_id, alias_address, alias_address)
            for alias_address in alias_addresses
        ]

    primary_usable_email = UsableEmail(
        id=require_inserted_id(email_cursor.lastrowid),
        address=primary_address,
        label=display_name,
        kind="primary",
        status="active",
    )
    return EmailAccount(
        id=account_id,
        provider=provider,
        primary_address=primary_address,
        display_name=display_name,
        status="active",
        primary_usable_email=primary_usable_email,
        usable_emails=(primary_usable_email, *alias_emails),
    )


def deactivate_email_account(
    settings: Settings, user_id: int, account_id: int
) -> EmailAccount | None:
    with connect(settings) as connection:
        account = connection.execute(
            """
            SELECT id, provider, primary_address, display_name
            FROM email_accounts
            WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id),
        ).fetchone()
        if account is None:
            return None

        connection.execute(
            """
            UPDATE email_accounts
            SET status = 'inactive'
            WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id),
        )
        email = connection.execute(
            """
            UPDATE usable_emails
            SET status = 'inactive', active = 0
            WHERE user_id = ? AND email_account_id = ?
            RETURNING id, address, label, kind, status
            """,
            (user_id, account_id),
        ).fetchall()

    usable_emails = tuple(usable_email_from_row(row) for row in email)
    primary_usable_email = next(email for email in usable_emails if email.kind == "primary")
    return EmailAccount(
        id=account["id"],
        provider=account["provider"],
        primary_address=account["primary_address"],
        display_name=account["display_name"],
        status="inactive",
        primary_usable_email=primary_usable_email,
        usable_emails=usable_emails,
    )


def get_email_account(settings: Settings, user_id: int, account_id: int) -> EmailAccount | None:
    with connect(settings) as connection:
        account = connection.execute(
            """
            SELECT id, provider, primary_address, display_name, status
            FROM email_accounts
            WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id),
        ).fetchone()
        if account is None:
            return None

        rows = connection.execute(
            """
            SELECT id, address, label, kind, status
            FROM usable_emails
            WHERE user_id = ? AND email_account_id = ?
            ORDER BY id
            """,
            (user_id, account_id),
        ).fetchall()

    usable_emails = tuple(usable_email_from_row(row) for row in rows)
    primary_usable_email = next(email for email in usable_emails if email.kind == "primary")
    return EmailAccount(
        id=account["id"],
        provider=account["provider"],
        primary_address=account["primary_address"],
        display_name=account["display_name"],
        status=account["status"],
        primary_usable_email=primary_usable_email,
        usable_emails=usable_emails,
    )


def add_alias_to_email_account(
    settings: Settings,
    user_id: int,
    account_id: int,
    address: str,
    label: str,
) -> UsableEmail | None:
    with connect(settings) as connection:
        account = connection.execute(
            "SELECT id FROM email_accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchone()
        if account is None:
            return None

        return add_alias_email(connection, user_id, account_id, address, label)
