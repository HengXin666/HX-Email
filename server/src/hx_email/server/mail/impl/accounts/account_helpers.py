"""Shared helpers for email account operations (no circular deps on email_accounts)."""

from __future__ import annotations

import sqlite3
from sqlite3 import Connection, Row

from hx_email.server.auth import require_inserted_id
from hx_email.server.mail.usable_emails import UsableEmail


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
