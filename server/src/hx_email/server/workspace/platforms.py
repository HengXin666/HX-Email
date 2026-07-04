import sqlite3
from dataclasses import dataclass
from email.utils import parseaddr
from sqlite3 import Row

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id


class DuplicatePlatformNameError(Exception):
    pass


class DuplicatePlatformBindingError(Exception):
    pass


class InvalidPlatformBindingStatusError(Exception):
    pass


VALID_BINDING_STATUSES = {
    "active",
    "pending_verification",
    "risk",
    "disabled",
    "archived",
}


@dataclass(frozen=True)
class Platform:
    id: int
    name: str
    binding_count: int = 0


@dataclass(frozen=True)
class PlatformBinding:
    id: int
    usable_email_id: int
    platform: Platform
    status: str
    notes: str


@dataclass(frozen=True)
class PlatformCandidate:
    name: str
    source: str


def suggest_platform_candidates(sender: str, subject: str, body: str) -> list[PlatformCandidate]:
    _, address = parseaddr(sender)
    if "@" not in address:
        return []

    domain = address.rsplit("@", 1)[1].lower()
    if not domain or "." not in domain:
        return []

    return [PlatformCandidate(name=domain, source="sender")]


def create_platform(settings: Settings, user_id: int, name: str) -> Platform:
    try:
        with connect(settings) as connection:
            cursor = connection.execute(
                "INSERT INTO platforms (user_id, name) VALUES (?, ?)",
                (user_id, name),
            )
    except sqlite3.IntegrityError as error:
        raise DuplicatePlatformNameError("Platform name already exists") from error

    return Platform(id=require_inserted_id(cursor.lastrowid), name=name)


def list_platforms(settings: Settings, user_id: int, query: str | None = None) -> list[Platform]:
    where = ["platforms.user_id = ?"]
    params: list[object] = [user_id]
    if query:
        where.append("platforms.name LIKE ?")
        params.append(f"%{query}%")

    with connect(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT platforms.id, platforms.name, COUNT(platform_bindings.id) AS binding_count
            FROM platforms
            LEFT JOIN platform_bindings ON platform_bindings.user_id = platforms.user_id
                AND platform_bindings.platform_id = platforms.id
            WHERE {" AND ".join(where)}
            GROUP BY platforms.id
            ORDER BY platforms.id
            """,
            params,
        ).fetchall()

    return [
        Platform(id=row["id"], name=row["name"], binding_count=row["binding_count"]) for row in rows
    ]


def update_platform(
    settings: Settings, user_id: int, platform_id: int, name: str
) -> Platform | None:
    try:
        with connect(settings) as connection:
            row = connection.execute(
                """
                UPDATE platforms
                SET name = ?
                WHERE id = ? AND user_id = ?
                RETURNING id, name
                """,
                (name, platform_id, user_id),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise DuplicatePlatformNameError("Platform name already exists") from error

    if row is None:
        return None
    return Platform(id=row["id"], name=row["name"])


def delete_platform(settings: Settings, user_id: int, platform_id: int) -> bool:
    with connect(settings) as connection:
        connection.execute(
            "DELETE FROM platform_bindings WHERE user_id = ? AND platform_id = ?",
            (user_id, platform_id),
        )
        result = connection.execute(
            "DELETE FROM platforms WHERE id = ? AND user_id = ?",
            (platform_id, user_id),
        )
    return result.rowcount > 0


def create_platform_binding(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    platform_id: int,
    status: str,
    notes: str,
) -> PlatformBinding | None:
    if status not in VALID_BINDING_STATUSES:
        raise InvalidPlatformBindingStatusError("Invalid platform binding status")

    with connect(settings) as connection:
        usable_email = connection.execute(
            "SELECT id FROM usable_emails WHERE id = ? AND user_id = ?",
            (usable_email_id, user_id),
        ).fetchone()
        platform = connection.execute(
            "SELECT id FROM platforms WHERE id = ? AND user_id = ?",
            (platform_id, user_id),
        ).fetchone()
        if usable_email is None or platform is None:
            return None

        try:
            cursor = connection.execute(
                """
                INSERT INTO platform_bindings (user_id, usable_email_id, platform_id, status, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, usable_email_id, platform_id, status, notes),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicatePlatformBindingError("Platform binding already exists") from error

    binding = get_platform_binding(settings, user_id, require_inserted_id(cursor.lastrowid))
    if binding is None:
        raise RuntimeError("Created platform binding could not be loaded")
    return binding


def list_platform_bindings(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> list[PlatformBinding] | None:
    with connect(settings) as connection:
        usable_email = connection.execute(
            "SELECT id FROM usable_emails WHERE id = ? AND user_id = ?",
            (usable_email_id, user_id),
        ).fetchone()
        if usable_email is None:
            return None

        rows = connection.execute(
            """
            SELECT platform_bindings.id, platform_bindings.usable_email_id,
                   platform_bindings.status, platform_bindings.notes,
                   platforms.id AS platform_id, platforms.name AS platform_name
            FROM platform_bindings
            JOIN platforms ON platforms.id = platform_bindings.platform_id
                AND platforms.user_id = platform_bindings.user_id
            WHERE platform_bindings.user_id = ? AND platform_bindings.usable_email_id = ?
            ORDER BY platform_bindings.id
            """,
            (user_id, usable_email_id),
        ).fetchall()

    return [binding_from_row(row) for row in rows]


def update_platform_binding(
    settings: Settings,
    user_id: int,
    binding_id: int,
    status: str,
    notes: str,
) -> PlatformBinding | None:
    if status not in VALID_BINDING_STATUSES:
        raise InvalidPlatformBindingStatusError("Invalid platform binding status")

    with connect(settings) as connection:
        row = connection.execute(
            """
            UPDATE platform_bindings
            SET status = ?, notes = ?
            WHERE id = ? AND user_id = ?
            RETURNING id
            """,
            (status, notes, binding_id, user_id),
        ).fetchone()

    if row is None:
        return None
    return get_platform_binding(settings, user_id, binding_id)


def get_platform_binding(
    settings: Settings, user_id: int, binding_id: int
) -> PlatformBinding | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT platform_bindings.id, platform_bindings.usable_email_id,
                   platform_bindings.status, platform_bindings.notes,
                   platforms.id AS platform_id, platforms.name AS platform_name
            FROM platform_bindings
            JOIN platforms ON platforms.id = platform_bindings.platform_id
                AND platforms.user_id = platform_bindings.user_id
            WHERE platform_bindings.id = ? AND platform_bindings.user_id = ?
            """,
            (binding_id, user_id),
        ).fetchone()

    if row is None:
        return None
    return binding_from_row(row)


def binding_from_row(row: Row) -> PlatformBinding:
    return PlatformBinding(
        id=row["id"],
        usable_email_id=row["usable_email_id"],
        platform=Platform(id=row["platform_id"], name=row["platform_name"]),
        status=row["status"],
        notes=row["notes"],
    )
