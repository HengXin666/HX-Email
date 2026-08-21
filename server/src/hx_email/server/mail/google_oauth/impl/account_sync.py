"""Persist Gmail OAuth credentials for the account discovered on the callback."""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import encrypt_secret
from hx_email.server.mail.email_accounts import add_email_account
from hx_email.server.mail.impl.patrol.options import assert_group_allows_provider


def update_account_credentials(
    settings: Settings,
    user_id: int,
    account_id: int,
    client_id: str,
    refresh_token: str,
    email: str,
) -> None:
    """Write Gmail OAuth credentials onto an existing email account."""
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            UPDATE email_accounts
            SET client_id = ?, refresh_token = ?, imap_password = '', username = ?,
                provider = 'gmail'
            WHERE id = ? AND user_id = ?
            """,
            (client_id, encrypt_secret(settings, refresh_token), email, account_id, user_id),
        )
    if cursor.rowcount != 1:
        raise RuntimeError("Email account no longer exists")


def save_credentials_by_email(
    settings: Settings,
    user_id: int,
    email: str,
    client_id: str,
    refresh_token: str,
    group_id: int | None,
) -> int:
    """Create or update the Gmail account owning ``email`` with OAuth credentials.

    When no account owns ``email`` yet, a Gmail account (plus its primary
    usable email) is created; otherwise the existing account is updated.
    Returns the account id.
    """
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id FROM email_accounts
            WHERE user_id = ? AND primary_address = ?
            """,
            (user_id, email),
        ).fetchone()
    if row is not None:
        account_id: int = int(row["id"])
        update_account_credentials(settings, user_id, account_id, client_id, refresh_token, email)
        if group_id is not None:
            assert_group_allows_provider(settings, user_id, group_id, "gmail")
            with connect(settings) as connection:
                connection.execute(
                    """
                    UPDATE email_accounts SET group_id = ? WHERE id = ? AND user_id = ?
                    """,
                    (group_id, account_id, user_id),
                )
        return account_id
    account = add_email_account(
        settings,
        user_id,
        "gmail",
        email,
        email,
        imap_host="imap.gmail.com",
        imap_port=993,
        username=email,
        imap_password="",
        client_id=client_id,
        refresh_token=refresh_token,
        alias_addresses=[],
        group_id=group_id,
    )
    return account.id
