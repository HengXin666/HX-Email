"""Database queries for verification — private implementation."""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail import EmailAccountMailbox
from hx_email.server.mail.usable_emails import UsableEmail


def load_target(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> tuple[UsableEmail, EmailAccountMailbox] | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT ue.id AS ue_id, ue.address, ue.label, ue.kind, ue.status, "
            "ea.id AS ea_id, ea.provider, ea.primary_address "
            "FROM usable_emails ue "
            "JOIN email_accounts ea ON ea.id = ue.email_account_id "
            "AND ea.user_id = ue.user_id "
            "WHERE ue.id = ? AND ue.user_id = ?",
            (usable_email_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return (
        UsableEmail(
            id=row["ue_id"],
            address=row["address"],
            label=row["label"],
            kind=row["kind"],
            status=row["status"],
        ),
        EmailAccountMailbox(
            id=row["ea_id"],
            provider=row["provider"],
            primary_address=row["primary_address"],
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
