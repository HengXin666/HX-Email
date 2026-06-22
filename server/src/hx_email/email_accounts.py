from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.usable_emails import UsableEmail


@dataclass(frozen=True)
class EmailAccount:
    id: int
    provider: str
    primary_address: str
    display_name: str
    status: str
    primary_usable_email: UsableEmail


def add_email_account(
    settings: Settings,
    user_id: int,
    provider: str,
    primary_address: str,
    display_name: str,
    imap_host: str = "",
    imap_port: int | None = None,
    username: str = "",
) -> EmailAccount:
    with connect(settings) as connection:
        account_cursor = connection.execute(
            """
            INSERT INTO email_accounts (
                user_id, provider, primary_address, display_name, imap_host, imap_port, username
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, provider, primary_address, display_name, imap_host, imap_port, username),
        )
        account_id = account_cursor.lastrowid
        email_cursor = connection.execute(
            """
            INSERT INTO usable_emails (user_id, email_account_id, address, label, kind, status, active)
            VALUES (?, ?, ?, ?, 'primary', 'active', 1)
            """,
            (user_id, account_id, primary_address, display_name),
        )

    primary_usable_email = UsableEmail(
        id=email_cursor.lastrowid,
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
    )


def deactivate_email_account(settings: Settings, user_id: int, account_id: int) -> EmailAccount | None:
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
            WHERE user_id = ? AND email_account_id = ? AND kind = 'primary'
            RETURNING id, address, label, kind, status
            """,
            (user_id, account_id),
        ).fetchone()

    return EmailAccount(
        id=account["id"],
        provider=account["provider"],
        primary_address=account["primary_address"],
        display_name=account["display_name"],
        status="inactive",
        primary_usable_email=UsableEmail(
            id=email["id"],
            address=email["address"],
            label=email["label"],
            kind=email["kind"],
            status=email["status"],
        ),
    )
