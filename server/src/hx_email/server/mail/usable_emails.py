from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id


@dataclass(frozen=True)
class GroupInfo:
    id: int
    name: str
    color: str


@dataclass(frozen=True)
class UsableEmail:
    id: int
    address: str
    label: str
    kind: str = "custom"
    status: str = "active"
    group: GroupInfo | None = None
    email_account_id: int | None = None


def group_info_from_row(row: Mapping[str, Any]) -> GroupInfo | None:
    """Extract GroupInfo from a joined row if group columns are present and non-NULL."""
    try:
        gid = row["group_id"]
    except (KeyError, IndexError):
        return None
    if gid is None:
        return None
    # sqlite3.Row is a tuple subclass, so "key in row" checks *values*, not keys.
    # Must use .keys() explicitly here; the SIM118 rule does not apply.
    keys = row.keys()
    name_raw = row["group_name"] if "group_name" in keys else None
    color_raw = row["group_color"] if "group_color" in keys else None
    return GroupInfo(
        id=int(gid),
        name=str(name_raw or ""),
        color=str(color_raw or ""),
    )


def add_usable_email(settings: Settings, user_id: int, address: str, label: str) -> UsableEmail:
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO usable_emails (user_id, address, label, kind, status, active)
            VALUES (?, ?, ?, 'custom', 'active', 1)
            """,
            (user_id, address, label),
        )

    return UsableEmail(
        id=require_inserted_id(cursor.lastrowid),
        address=address,
        label=label,
        kind="custom",
        status="active",
    )


def list_usable_emails(settings: Settings, user_id: int) -> list[UsableEmail]:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT ue.id, ue.address, ue.label, ue.kind, ue.status,
                   ue.email_account_id,
                   ue.group_id, g.name AS group_name, g.color AS group_color
            FROM usable_emails ue
            LEFT JOIN groups g ON g.id = ue.group_id
            WHERE ue.user_id = ?
            ORDER BY ue.active DESC, ue.id
            """,
            (user_id,),
        ).fetchall()

    return [
        UsableEmail(
            id=row["id"],
            address=row["address"],
            label=row["label"],
            kind=row["kind"],
            status=row["status"],
            group=group_info_from_row(row),
            email_account_id=row["email_account_id"],
        )
        for row in rows
    ]


def get_usable_email(settings: Settings, user_id: int, usable_email_id: int) -> UsableEmail | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT ue.id, ue.address, ue.label, ue.kind, ue.status,
                   ue.group_id, g.name AS group_name, g.color AS group_color
            FROM usable_emails ue
            LEFT JOIN groups g ON g.id = ue.group_id
            WHERE ue.id = ? AND ue.user_id = ?
            """,
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
        group=group_info_from_row(row),
    )


def deactivate_usable_email(
    settings: Settings, user_id: int, usable_email_id: int
) -> UsableEmail | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            UPDATE usable_emails
            SET status = 'inactive', active = 0
            WHERE id = ? AND user_id = ?
            RETURNING id, address, label, kind, status, group_id
            """,
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
        group=group_info_from_row(row),
    )


def delete_usable_email(settings: Settings, user_id: int, usable_email_id: int) -> bool:
    """Hard-delete a standalone usable_email and ALL associated data (cascade).

    Only use for emails WITHOUT an email_account_id (e.g. custom/temp emails).
    For emails with an account, use delete_email_account instead.
    """
    with connect(settings) as connection:
        # 1) Verify the email exists and has no email_account_id
        row = connection.execute(
            "SELECT id, email_account_id FROM usable_emails WHERE id = ? AND user_id = ?",
            (usable_email_id, user_id),
        ).fetchone()
        if row is None:
            return False
        if row["email_account_id"] is not None:
            # Refuse to partially delete an account-linked email — use delete_email_account
            return False

        # 2) Cascade-delete all child tables
        connection.execute(
            "DELETE FROM usable_email_tags WHERE usable_email_id = ?", (usable_email_id,)
        )
        connection.execute(
            "DELETE FROM platform_bindings WHERE usable_email_id = ? AND user_id = ?",
            (usable_email_id, user_id),
        )
        connection.execute(
            "DELETE FROM mail_pool_entries WHERE usable_email_id = ? AND user_id = ?",
            (usable_email_id, user_id),
        )
        connection.execute(
            "DELETE FROM verification_readings WHERE usable_email_id = ? AND user_id = ?",
            (usable_email_id, user_id),
        )
        connection.execute(
            "DELETE FROM temp_mailboxes WHERE usable_email_id = ? AND user_id = ?",
            (usable_email_id, user_id),
        )

        # 3) Delete the email itself
        cursor = connection.execute(
            "DELETE FROM usable_emails WHERE id = ? AND user_id = ?",
            (usable_email_id, user_id),
        )
    return cursor.rowcount > 0
