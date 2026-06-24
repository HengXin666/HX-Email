from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id
from hx_email.server.mail.impl.accounts.account_helpers import (
    DuplicateUsableEmailError,
    InvalidAliasAddressError,  # re-exported
    add_alias_email,
    usable_email_from_row,
)
from hx_email.server.mail.usable_emails import UsableEmail

__all__ = [
    "DuplicateUsableEmailError",
    "EmailAccount",
    "InvalidAliasAddressError",
    "add_alias_to_email_account",
    "add_email_account",
    "deactivate_email_account",
    "get_email_account",
    "list_email_accounts",
    "usable_email_from_row",
]


@dataclass(frozen=True)
class EmailAccount:
    id: int
    provider: str
    primary_address: str
    display_name: str
    status: str
    primary_usable_email: UsableEmail
    imap_host: str = ""
    imap_port: int | None = None
    username: str = ""
    imap_password: str = ""
    client_id: str = ""
    refresh_token: str = ""
    group_id: int | None = None
    remark: str = ""
    telegram_enabled: bool = True
    usable_emails: tuple[UsableEmail, ...] = ()


def add_email_account(
    settings: Settings,
    user_id: int,
    provider: str,
    primary_address: str,
    display_name: str,
    imap_host: str = "",
    imap_port: int | None = None,
    username: str = "",
    imap_password: str = "",
    client_id: str = "",
    refresh_token: str = "",
    alias_addresses: list[str] | None = None,
) -> EmailAccount:
    alias_addresses = alias_addresses or []
    with connect(settings) as connection:
        try:
            account_cursor = connection.execute(
                """
                INSERT INTO email_accounts (
                    user_id, provider, primary_address, display_name, imap_host,
                    imap_port, username, imap_password, client_id, refresh_token
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    provider,
                    primary_address,
                    display_name,
                    imap_host,
                    imap_port,
                    username,
                    imap_password,
                    client_id,
                    refresh_token,
                ),
            )
        except Exception as error:
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
        except Exception as error:
            raise DuplicateUsableEmailError(
                "Usable email address already exists for this user"
            ) from error
        alias_emails = [
            add_alias_email(connection, user_id, account_id, addr, addr) for addr in alias_addresses
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
        imap_host=imap_host,
        imap_port=imap_port,
        username=username,
        imap_password=imap_password,
        client_id=client_id,
        refresh_token=refresh_token,
        usable_emails=(primary_usable_email, *alias_emails),
    )


def deactivate_email_account(
    settings: Settings, user_id: int, account_id: int
) -> EmailAccount | None:
    with connect(settings) as connection:
        account = connection.execute(
            """
            SELECT id, provider, primary_address, display_name, imap_host,
                   imap_port, username, imap_password, client_id, refresh_token,
                   group_id, remark, telegram_enabled
            FROM email_accounts
            WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id),
        ).fetchone()
        if account is None:
            return None
        connection.execute(
            """
            UPDATE email_accounts SET status = 'inactive' WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id),
        )
        email = connection.execute(
            """
            UPDATE usable_emails SET status = 'inactive', active = 0
            WHERE user_id = ? AND email_account_id = ?
            RETURNING id, address, label, kind, status
            """,
            (user_id, account_id),
        ).fetchall()
    usable_emails = tuple(usable_email_from_row(row) for row in email)
    primary_usable_email = next(e for e in usable_emails if e.kind == "primary")
    return EmailAccount(
        id=account["id"],
        provider=account["provider"],
        primary_address=account["primary_address"],
        display_name=account["display_name"],
        status="inactive",
        primary_usable_email=primary_usable_email,
        imap_host=account["imap_host"],
        imap_port=account["imap_port"],
        username=account["username"],
        imap_password=account["imap_password"],
        client_id=account["client_id"],
        refresh_token=account["refresh_token"],
        group_id=account["group_id"],
        remark=account["remark"] or "",
        telegram_enabled=bool(account["telegram_enabled"]),
        usable_emails=usable_emails,
    )


def get_email_account(settings: Settings, user_id: int, account_id: int) -> EmailAccount | None:
    with connect(settings) as connection:
        account = connection.execute(
            """
            SELECT id, provider, primary_address, display_name, status, imap_host,
                   imap_port, username, imap_password, client_id, refresh_token,
                   group_id, remark, telegram_enabled
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
    primary_usable_email = next(e for e in usable_emails if e.kind == "primary")
    return EmailAccount(
        id=account["id"],
        provider=account["provider"],
        primary_address=account["primary_address"],
        display_name=account["display_name"],
        status=account["status"],
        primary_usable_email=primary_usable_email,
        imap_host=account["imap_host"],
        imap_port=account["imap_port"],
        username=account["username"],
        imap_password=account["imap_password"],
        client_id=account["client_id"],
        refresh_token=account["refresh_token"],
        group_id=account["group_id"],
        remark=account["remark"] or "",
        telegram_enabled=bool(account["telegram_enabled"]),
        usable_emails=usable_emails,
    )


def list_email_accounts(settings: Settings, user_id: int) -> tuple[EmailAccount, ...]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT id FROM email_accounts WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    accounts = (get_email_account(settings, user_id, row["id"]) for row in rows)
    return tuple(a for a in accounts if a is not None)


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
