import sqlite3
from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id
from hx_email.server.mail.usable_emails import UsableEmail

POOL_STATUSES: frozenset[str] = frozenset({"available", "claimed", "completed", "cooling"})


class DuplicateMailPoolEntryError(ValueError):
    pass


@dataclass(frozen=True)
class MailPoolEntry:
    id: int
    usable_email: UsableEmail
    status: str
    claim_key: str
    claimed_project_key: str
    completed_project_key: str


def add_mail_pool_entry(
    settings: Settings, user_id: int, usable_email_id: int
) -> MailPoolEntry | None:
    with connect(settings) as connection:
        usable_email = connection.execute(
            "SELECT id FROM usable_emails WHERE id = ? AND user_id = ?",
            (usable_email_id, user_id),
        ).fetchone()
        if usable_email is None:
            return None
        try:
            cursor = connection.execute(
                """
                INSERT INTO mail_pool_entries (user_id, usable_email_id, status)
                VALUES (?, ?, 'available')
                """,
                (user_id, usable_email_id),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateMailPoolEntryError("Usable email is already in the mail pool") from error

    entry = get_mail_pool_entry(settings, user_id, require_inserted_id(cursor.lastrowid))
    if entry is None:
        raise RuntimeError("Created mail pool entry could not be loaded")
    return entry


def remove_mail_pool_entry(settings: Settings, user_id: int, usable_email_id: int) -> bool:
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            DELETE FROM mail_pool_entries
            WHERE usable_email_id = ? AND user_id = ?
            """,
            (usable_email_id, user_id),
        )
    return cursor.rowcount > 0


def list_mail_pool_entries(settings: Settings, user_id: int) -> tuple[MailPoolEntry, ...]:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT mail_pool_entries.id AS entry_id,
                   mail_pool_entries.status,
                   mail_pool_entries.claim_key,
                   mail_pool_entries.claimed_project_key,
                   mail_pool_entries.completed_project_key,
                   usable_emails.id AS usable_email_id,
                   usable_emails.address,
                   usable_emails.label,
                   usable_emails.kind,
                   usable_emails.status AS usable_email_status
            FROM mail_pool_entries
            JOIN usable_emails ON usable_emails.id = mail_pool_entries.usable_email_id
                AND usable_emails.user_id = mail_pool_entries.user_id
            WHERE mail_pool_entries.user_id = ?
            ORDER BY mail_pool_entries.id
            """,
            (user_id,),
        ).fetchall()
    return tuple(entry_from_row(row) for row in rows)


def claim_mail_pool_entry(
    settings: Settings,
    user_id: int,
    project_key: str,
    claim_key: str,
) -> MailPoolEntry | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT mail_pool_entries.id
            FROM mail_pool_entries
            JOIN usable_emails ON usable_emails.id = mail_pool_entries.usable_email_id
                AND usable_emails.user_id = mail_pool_entries.user_id
            WHERE mail_pool_entries.user_id = ?
                AND mail_pool_entries.status IN ('available', 'completed')
                AND usable_emails.status = 'active'
                AND mail_pool_entries.completed_project_key != ?
            ORDER BY mail_pool_entries.id
            LIMIT 1
            """,
            (user_id, project_key),
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            """
            UPDATE mail_pool_entries
            SET status = 'claimed', claim_key = ?, claimed_project_key = ?
            WHERE id = ? AND user_id = ?
            """,
            (claim_key, project_key, row["id"], user_id),
        )

    return get_mail_pool_entry(settings, user_id, row["id"])


def release_mail_pool_entry(
    settings: Settings, user_id: int, usable_email_id: int
) -> MailPoolEntry | None:
    return set_pool_status(
        settings,
        user_id,
        usable_email_id,
        "available",
        claim_key="",
        claimed_project_key="",
    )


def complete_mail_pool_entry(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    project_key: str,
) -> MailPoolEntry | None:
    return set_pool_status(
        settings,
        user_id,
        usable_email_id,
        "completed",
        completed_project_key=project_key,
    )


def cooldown_mail_pool_entry(
    settings: Settings, user_id: int, usable_email_id: int
) -> MailPoolEntry | None:
    return set_pool_status(settings, user_id, usable_email_id, "cooling")


def set_pool_status(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    status: str,
    *,
    claim_key: str | None = None,
    claimed_project_key: str | None = None,
    completed_project_key: str | None = None,
) -> MailPoolEntry | None:
    if status not in POOL_STATUSES:
        raise ValueError("Invalid mail pool status")
    assignments = ["status = ?"]
    params: list[object] = [status]
    if claim_key is not None:
        assignments.append("claim_key = ?")
        params.append(claim_key)
    if claimed_project_key is not None:
        assignments.append("claimed_project_key = ?")
        params.append(claimed_project_key)
    if completed_project_key is not None:
        assignments.append("completed_project_key = ?")
        params.append(completed_project_key)
    params.extend([usable_email_id, user_id])
    with connect(settings) as connection:
        row = connection.execute(
            f"""
            UPDATE mail_pool_entries
            SET {", ".join(assignments)}
            WHERE usable_email_id = ? AND user_id = ?
            RETURNING id
            """,
            params,
        ).fetchone()
    if row is None:
        return None
    return get_mail_pool_entry(settings, user_id, row["id"])


def get_mail_pool_entry(settings: Settings, user_id: int, entry_id: int) -> MailPoolEntry | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT mail_pool_entries.id AS entry_id,
                   mail_pool_entries.status,
                   mail_pool_entries.claim_key,
                   mail_pool_entries.claimed_project_key,
                   mail_pool_entries.completed_project_key,
                   usable_emails.id AS usable_email_id,
                   usable_emails.address,
                   usable_emails.label,
                   usable_emails.kind,
                   usable_emails.status AS usable_email_status
            FROM mail_pool_entries
            JOIN usable_emails ON usable_emails.id = mail_pool_entries.usable_email_id
                AND usable_emails.user_id = mail_pool_entries.user_id
            WHERE mail_pool_entries.id = ? AND mail_pool_entries.user_id = ?
            """,
            (entry_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return entry_from_row(row)


def entry_from_row(row: sqlite3.Row) -> MailPoolEntry:
    return MailPoolEntry(
        id=row["entry_id"],
        usable_email=UsableEmail(
            id=row["usable_email_id"],
            address=row["address"],
            label=row["label"],
            kind=row["kind"],
            status=row["usable_email_status"],
        ),
        status=row["status"],
        claim_key=row["claim_key"],
        claimed_project_key=row["claimed_project_key"],
        completed_project_key=row["completed_project_key"],
    )
