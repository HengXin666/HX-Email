from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id


@dataclass(frozen=True)
class UsableEmail:
    id: int
    address: str
    label: str
    kind: str = "custom"
    status: str = "active"


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
            SELECT id, address, label, kind, status
            FROM usable_emails
            WHERE user_id = ? AND active = 1
            ORDER BY id
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
        )
        for row in rows
    ]


def get_usable_email(settings: Settings, user_id: int, usable_email_id: int) -> UsableEmail | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id, address, label, kind, status
            FROM usable_emails
            WHERE id = ? AND user_id = ?
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
            RETURNING id, address, label, kind, status
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
    )
