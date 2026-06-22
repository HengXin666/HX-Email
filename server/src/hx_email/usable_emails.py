from dataclasses import dataclass

from hx_email.database import connect
from hx_email.config import Settings


@dataclass(frozen=True)
class UsableEmail:
    id: int
    address: str
    label: str


def add_usable_email(settings: Settings, user_id: int, address: str, label: str) -> UsableEmail:
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO usable_emails (user_id, address, label)
            VALUES (?, ?, ?)
            """,
            (user_id, address, label),
        )

    return UsableEmail(id=cursor.lastrowid, address=address, label=label)


def list_usable_emails(settings: Settings, user_id: int) -> list[UsableEmail]:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, address, label
            FROM usable_emails
            WHERE user_id = ? AND active = 1
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()

    return [UsableEmail(id=row["id"], address=row["address"], label=row["label"]) for row in rows]
