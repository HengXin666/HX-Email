import sqlite3
from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect, utc_now_iso
from hx_email.security import decrypt_secret, encrypt_secret
from hx_email.server.auth import require_inserted_id
from hx_email.server.mail.imap.impl.address_guard import validate_proxy_host as validate_imap_host
from hx_email.server.mail.impl.accounts.account_helpers import (
    DuplicateUsableEmailError,
    InvalidAliasAddressError,  # re-exported
    add_alias_email,
    usable_email_from_row,
)
from hx_email.server.mail.impl.patrol.options import assert_group_allows_provider
from hx_email.server.mail.usable_emails import UsableEmail

__all__ = [
    "DuplicateUsableEmailError",
    "EmailAccount",
    "InvalidAliasAddressError",
    "add_alias_to_email_account",
    "add_email_account",
    "deactivate_email_account",
    "get_email_account",
    "get_email_accounts",
    "has_active_email_account",
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
    last_refresh_at: str | None = None
    created_at: str = ""
    last_fetch_at: str | None = None
    refresh_failed_at: str | None = None
    usable_emails: tuple[UsableEmail, ...] = ()


def has_active_email_account(settings: Settings, user_id: int, account_id: int) -> bool:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT 1 FROM email_accounts WHERE id = ? AND user_id = ? AND status = 'active'",
            (account_id, user_id),
        ).fetchone()
    return row is not None


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
    group_id: int | None = None,
) -> EmailAccount:
    if imap_host.strip():
        validate_imap_host(imap_host)
    alias_addresses = alias_addresses or []
    created_at: str = utc_now_iso()
    with connect(settings) as connection:
        if group_id is not None:
            assert_group_allows_provider(settings, user_id, group_id, provider, connection)
        try:
            account_cursor = connection.execute(
                """
                INSERT INTO email_accounts (
                    user_id, provider, primary_address, display_name, imap_host,
                    imap_port, username, imap_password, client_id, refresh_token, group_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    encrypt_secret(settings, refresh_token),
                    group_id,
                    created_at,
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
                    user_id, email_account_id, address, label, kind, status, active, group_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'primary', 'active', 1, ?, ?)
                """,
                (user_id, account_id, primary_address, display_name, group_id, created_at),
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
        created_at=created_at,
        email_account_id=account_id,
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
        group_id=group_id,
        created_at=created_at,
        usable_emails=(primary_usable_email, *alias_emails),
    )


def deactivate_email_account(
    settings: Settings, user_id: int, account_id: int
) -> EmailAccount | None:
    with connect(settings) as connection:
        cursor = connection.execute(
            "UPDATE email_accounts SET status = 'inactive' WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        )
        if cursor.rowcount == 0:
            return None
        email = connection.execute(
            """
            UPDATE usable_emails SET status = 'inactive', active = 0
            WHERE user_id = ? AND email_account_id = ?
            RETURNING id, address, label, kind, status, created_at
            """,
            (user_id, account_id),
        ).fetchall()
        account = connection.execute(
            """
            SELECT id, provider, primary_address, display_name, status, imap_host,
                   imap_port, username, imap_password, client_id, refresh_token,
                   group_id, remark, telegram_enabled, last_refresh_at,
                   created_at, last_fetch_at, refresh_failed_at
            FROM email_accounts
            WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id),
        ).fetchone()
    return build_account_from_row(settings, account, email)


def get_email_account(settings: Settings, user_id: int, account_id: int) -> EmailAccount | None:
    return get_email_accounts(settings, user_id, [account_id]).get(account_id)


def get_email_accounts(
    settings: Settings,
    user_id: int,
    account_ids: list[int],
) -> dict[int, EmailAccount]:
    """批量读取账号 (单连接 + IN 查询), 避免逐账号 connect 的 N+1 连接风暴."""
    if not account_ids:
        return {}
    unique_ids: list[int] = list(dict.fromkeys(account_ids))
    placeholders: str = ",".join("?" for _ in unique_ids)
    with connect(settings) as connection:
        account_rows = connection.execute(
            f"""
            SELECT id, provider, primary_address, display_name, status, imap_host,
                   imap_port, username, imap_password, client_id, refresh_token,
                   group_id, remark, telegram_enabled, last_refresh_at,
                   created_at, last_fetch_at, refresh_failed_at
            FROM email_accounts WHERE user_id = ? AND id IN ({placeholders})
            """,
            (user_id, *unique_ids),
        ).fetchall()
        email_rows = connection.execute(
            f"""
            SELECT id, address, label, kind, status, created_at, email_account_id
            FROM usable_emails
            WHERE user_id = ? AND email_account_id IN ({placeholders}) ORDER BY id
            """,
            (user_id, *unique_ids),
        ).fetchall()
    emails_by_account: dict[int, list[sqlite3.Row]] = {}
    for row in email_rows:
        key: int = int(row["email_account_id"])
        emails_by_account.setdefault(key, []).append(row)
    result: dict[int, EmailAccount] = {}
    for account in account_rows:
        account_id_value: int = int(account["id"])
        result[account_id_value] = build_account_from_row(
            settings, account, emails_by_account.get(account_id_value, [])
        )
    return result


def build_account_from_row(
    settings: Settings,
    account: sqlite3.Row,
    usable_rows: list[sqlite3.Row],
) -> EmailAccount:
    """从 email_accounts/usable_emails 行构造 EmailAccount (共享构造逻辑)。"""
    usable_emails = tuple(usable_email_from_row(row) for row in usable_rows)
    return EmailAccount(
        id=account["id"],
        provider=account["provider"],
        primary_address=account["primary_address"],
        display_name=account["display_name"],
        status=account["status"],
        primary_usable_email=next(e for e in usable_emails if e.kind == "primary"),
        imap_host=account["imap_host"],
        imap_port=account["imap_port"],
        username=account["username"],
        imap_password=account["imap_password"],
        client_id=account["client_id"],
        refresh_token=decrypt_secret(settings, str(account["refresh_token"] or "")),
        group_id=account["group_id"],
        remark=account["remark"] or "",
        telegram_enabled=bool(account["telegram_enabled"]),
        last_refresh_at=account["last_refresh_at"],
        created_at=account["created_at"] or "",
        last_fetch_at=account["last_fetch_at"],
        refresh_failed_at=account["refresh_failed_at"],
        usable_emails=usable_emails,
    )


def list_email_accounts(settings: Settings, user_id: int) -> tuple[EmailAccount, ...]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT id FROM email_accounts WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    ids: list[int] = [int(row["id"]) for row in rows]
    accounts_map: dict[int, EmailAccount] = get_email_accounts(settings, user_id, ids)
    return tuple(accounts_map[account_id] for account_id in ids if account_id in accounts_map)


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
