from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id


@dataclass(frozen=True)
class Group:
    id: int
    name: str
    color: str


@dataclass(frozen=True)
class Tag:
    id: int
    name: str
    color: str


def create_group(settings: Settings, user_id: int, name: str, color: str) -> Group:
    with connect(settings) as connection:
        cursor = connection.execute(
            "INSERT INTO groups (user_id, name, color) VALUES (?, ?, ?)",
            (user_id, name, color),
        )
    return Group(id=require_inserted_id(cursor.lastrowid), name=name, color=color)


def create_tag(settings: Settings, user_id: int, name: str, color: str) -> Tag:
    with connect(settings) as connection:
        cursor = connection.execute(
            "INSERT INTO tags (user_id, name, color) VALUES (?, ?, ?)",
            (user_id, name, color),
        )
    return Tag(id=require_inserted_id(cursor.lastrowid), name=name, color=color)


def list_groups(settings: Settings, user_id: int) -> list[Group]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT id, name, color FROM groups WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [Group(id=row["id"], name=row["name"], color=row["color"]) for row in rows]


def update_group(
    settings: Settings, user_id: int, group_id: int, name: str, color: str
) -> Group | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            UPDATE groups
            SET name = ?, color = ?
            WHERE id = ? AND user_id = ?
            RETURNING id, name, color
            """,
            (name, color, group_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return Group(id=row["id"], name=row["name"], color=row["color"])


def delete_group(settings: Settings, user_id: int, group_id: int) -> bool:
    with connect(settings) as connection:
        result = connection.execute(
            "DELETE FROM groups WHERE id = ? AND user_id = ?",
            (group_id, user_id),
        )
    return result.rowcount > 0


def list_tags(settings: Settings, user_id: int) -> list[Tag]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT id, name, color FROM tags WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [Tag(id=row["id"], name=row["name"], color=row["color"]) for row in rows]
