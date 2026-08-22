from __future__ import annotations

from typing import TYPE_CHECKING

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import encrypt_secret
from hx_email.server.mail.imap.message_store import delete_messages_for_email
from hx_email.server.mail.impl.accounts.account_helpers import update_primary_usable_email

if TYPE_CHECKING:
    from hx_email.server.mail.email_accounts import EmailAccount


def _get_email_account(settings: Settings, user_id: int, account_id: int) -> EmailAccount | None:
    from hx_email.server.mail.email_accounts import get_email_account as _gea

    return _gea(settings, user_id, account_id)


def update_email_account(
    settings: Settings,
    user_id: int,
    account_id: int,
    email: str | None = None,
    password: str | None = None,
    client_id: str | None = None,
    refresh_token: str | None = None,
    group_id: int | None = None,
    remark: str | None = None,
    status: str | None = None,
    provider: str | None = None,
    imap_host: str | None = None,
    imap_port: int | None = None,
) -> EmailAccount | None:
    existing = _get_email_account(settings, user_id, account_id)
    if existing is None:
        return None
    with connect(settings) as connection:
        sets: list[str] = []
        params: list[object] = []
        if email is not None:
            normalized_email: str = update_primary_usable_email(
                connection, user_id, account_id, email
            )
            sets.append("primary_address = ?")
            params.append(normalized_email)
            if normalized_email != existing.primary_address.strip().lower():
                sets.append("refresh_token = ''")
        if password is not None:
            sets.append("imap_password = ?")
            params.append(password)
        if client_id is not None:
            sets.append("client_id = ?")
            params.append(client_id)
        if refresh_token is not None:
            sets.append("refresh_token = ?")
            params.append(encrypt_secret(settings, refresh_token))
        if group_id is not None:
            sets.append("group_id = ?")
            params.append(group_id)
        if remark is not None:
            sets.append("remark = ?")
            params.append(remark)
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if provider is not None:
            sets.append("provider = ?")
            params.append(provider)
        if imap_host is not None:
            sets.append("imap_host = ?")
            params.append(imap_host)
        if imap_port is not None:
            sets.append("imap_port = ?")
            params.append(imap_port)
        if not sets:
            return existing
        params.append(account_id)
        params.append(user_id)
        connection.execute(
            f"UPDATE email_accounts SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
            params,
        )
        if status is not None:
            new_active = 1 if status == "active" else 0
            connection.execute(
                "UPDATE usable_emails SET status = ?, active = ?"
                " WHERE email_account_id = ? AND user_id = ?",
                (status, new_active, account_id, user_id),
            )
    return _get_email_account(settings, user_id, account_id)


def delete_email_account(settings: Settings, user_id: int, account_id: int) -> bool:
    """Hard-delete an email account and all associated data (cascade)."""
    with connect(settings) as connection:
        email_ids_rows = connection.execute(
            "SELECT id FROM usable_emails WHERE email_account_id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchall()
        email_ids = [row["id"] for row in email_ids_rows]
        for eid in email_ids:
            connection.execute("DELETE FROM usable_email_tags WHERE usable_email_id = ?", (eid,))
            connection.execute(
                "DELETE FROM platform_bindings WHERE usable_email_id = ? AND user_id = ?",
                (eid, user_id),
            )
            connection.execute(
                "DELETE FROM mail_pool_entries WHERE usable_email_id = ? AND user_id = ?",
                (eid, user_id),
            )
            connection.execute(
                "DELETE FROM verification_readings WHERE usable_email_id = ? AND user_id = ?",
                (eid, user_id),
            )
            connection.execute(
                "DELETE FROM temp_mailboxes WHERE usable_email_id = ? AND user_id = ?",
                (eid, user_id),
            )
            delete_messages_for_email(settings, eid, connection=connection)
        connection.execute(
            "DELETE FROM usable_emails WHERE email_account_id = ? AND user_id = ?",
            (account_id, user_id),
        )
        connection.execute("DELETE FROM refresh_logs WHERE account_id = ?", (account_id,))
        cursor = connection.execute(
            "DELETE FROM email_accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        )
    return cursor.rowcount > 0


def delete_email_account_by_email(settings: Settings, user_id: int, email_addr: str) -> bool:
    """Hard-delete an email account by primary address with full cascade."""
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT id FROM email_accounts WHERE user_id = ? AND primary_address = ?",
            (user_id, email_addr),
        ).fetchone()
        if row is None:
            return False
        return delete_email_account(settings, user_id, row["id"])


def update_account_remark(
    settings: Settings, user_id: int, account_id: int, remark: str
) -> EmailAccount | None:
    """Update only the remark field of an account."""
    with connect(settings) as connection:
        cursor = connection.execute(
            "UPDATE email_accounts SET remark = ? WHERE id = ? AND user_id = ?",
            (remark, account_id, user_id),
        )
    if cursor.rowcount == 0:
        return None
    return _get_email_account(settings, user_id, account_id)


def toggle_telegram_notification(
    settings: Settings, user_id: int, account_id: int, enabled: bool
) -> bool:
    """Toggle telegram notifications for a single account."""
    with connect(settings) as connection:
        cursor = connection.execute(
            "UPDATE email_accounts SET telegram_enabled = ? WHERE id = ? AND user_id = ?",
            (1 if enabled else 0, account_id, user_id),
        )
    return cursor.rowcount > 0
