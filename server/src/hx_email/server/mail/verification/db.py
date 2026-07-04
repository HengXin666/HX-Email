"""Database queries for verification — private implementation."""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail import EmailAccountMailbox
from hx_email.server.mail.usable_emails import UsableEmail
from hx_email.server.mail.verification.addresses import normalize_delivery_address


def load_target(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> tuple[UsableEmail, EmailAccountMailbox] | None:
    with connect(settings) as connection:
        usable_row = connection.execute(
            "SELECT id, address, label, kind, status, email_account_id "
            "FROM usable_emails WHERE id = ? AND user_id = ?",
            (usable_email_id, user_id),
        ).fetchone()
        if usable_row is None:
            return None

        account_row = None
        if usable_row["email_account_id"] is not None:
            account_row = connection.execute(
                "SELECT id, provider, primary_address FROM email_accounts "
                "WHERE id = ? AND user_id = ?",
                (usable_row["email_account_id"], user_id),
            ).fetchone()
        normalized_address: str = normalize_delivery_address(str(usable_row["address"]))
        if account_row is None and "@" in normalized_address:
            account_rows = connection.execute(
                """
                SELECT ea.id, ea.provider, ea.primary_address, ue.address
                FROM usable_emails ue
                JOIN email_accounts ea ON ea.id = ue.email_account_id
                WHERE ue.user_id = ? AND ea.user_id = ?
                  AND ue.email_account_id IS NOT NULL
                """,
                (user_id, user_id),
            ).fetchall()
            account_row = next(
                (
                    row
                    for row in account_rows
                    if normalize_delivery_address(str(row["address"] or "")) == normalized_address
                ),
                None,
            )
    if account_row is None:
        return None
    return (
        UsableEmail(
            id=usable_row["id"],
            address=usable_row["address"],
            label=usable_row["label"],
            kind=usable_row["kind"],
            status=usable_row["status"],
        ),
        EmailAccountMailbox(
            id=account_row["id"],
            provider=account_row["provider"],
            primary_address=account_row["primary_address"],
        ),
    )


def load_usable_email(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> UsableEmail | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT id, address, label, kind, status FROM usable_emails "
            "WHERE id = ? AND user_id = ?",
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
