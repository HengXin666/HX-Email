from dataclasses import dataclass
from sqlite3 import Connection
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.auth import require_inserted_id
from hx_email.server.settings_service import get_setting


@dataclass(frozen=True)
class Group:
    id: int
    name: str
    color: str
    proxy_url: str = ""
    notify_enabled: bool = True
    polling_enabled: bool = True
    sort_order: int = 0
    allowed_provider: str = ""


@dataclass(frozen=True)
class Tag:
    id: int
    name: str
    color: str


def create_group(
    settings: Settings,
    user_id: int,
    name: str,
    color: str,
    proxy_url: str = "",
    notify_enabled: bool | None = None,
    polling_enabled: bool | None = None,
    allowed_provider: str = "",
) -> Group:
    if not proxy_url:
        proxy_url = get_setting(settings, "group_default_proxy_url", "")
    if notify_enabled is None:
        notify_enabled = get_setting(settings, "group_default_notify_enabled", "true") == "true"
    if polling_enabled is None:
        polling_enabled = get_setting(settings, "group_default_polling_enabled", "true") == "true"
    with connect(settings) as connection:
        next_order: int = next_sort_order(connection, user_id)
        cursor = connection.execute(
            """
            INSERT INTO groups
                (user_id, name, color, proxy_url, notify_enabled, polling_enabled, sort_order,
                 allowed_provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name,
                color,
                proxy_url,
                int(notify_enabled),
                int(polling_enabled),
                next_order,
                allowed_provider,
            ),
        )
    return Group(
        id=require_inserted_id(cursor.lastrowid),
        name=name,
        color=color,
        proxy_url=proxy_url,
        notify_enabled=notify_enabled,
        polling_enabled=polling_enabled,
        sort_order=next_order,
        allowed_provider=allowed_provider,
    )


def create_tag(settings: Settings, user_id: int, name: str, color: str) -> Tag:
    with connect(settings) as connection:
        cursor = connection.execute(
            "INSERT INTO tags (user_id, name, color) VALUES (?, ?, ?)",
            (user_id, name, color),
        )
    return Tag(id=require_inserted_id(cursor.lastrowid), name=name, color=color)


def coerce_bool(value: object, default: bool) -> bool:
    """Coerce an import payload boolean, falling back to default when missing."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def next_sort_order(connection: Connection, user_id: int) -> int:
    """Return the sort_order to append a new group at the end of the user's list."""
    row = connection.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM groups WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return int(row["next_order"])


def import_groups(
    settings: Settings, connection: Connection, user_id: int, payload: dict[str, Any]
) -> dict[int, int]:
    """Import groups from a transfer payload, applying system defaults for omitted options."""
    default_proxy_url: str = get_setting(settings, "group_default_proxy_url", "")
    default_notify: bool = get_setting(settings, "group_default_notify_enabled", "true") == "true"
    default_polling: bool = get_setting(settings, "group_default_polling_enabled", "true") == "true"
    ids: dict[int, int] = {}
    for group in payload.get("groups", []):
        cursor = connection.execute(
            "INSERT INTO groups (user_id, name, color, proxy_url, notify_enabled, polling_enabled,"
            " sort_order, allowed_provider) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                group["name"],
                group.get("color", "#58a6ff"),
                group.get("proxy_url") or default_proxy_url,
                int(coerce_bool(group.get("notify_enabled"), default_notify)),
                int(coerce_bool(group.get("polling_enabled"), default_polling)),
                next_sort_order(connection, user_id),
                group.get("allowed_provider", ""),
            ),
        )
        ids[int(group["id"])] = require_inserted_id(cursor.lastrowid)
    return ids


def list_groups(settings: Settings, user_id: int) -> list[Group]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT id, name, color, proxy_url, notify_enabled, polling_enabled, sort_order,"
            " allowed_provider FROM groups WHERE user_id = ? ORDER BY sort_order, id",
            (user_id,),
        ).fetchall()
    return [
        Group(
            id=row["id"],
            name=row["name"],
            color=row["color"],
            proxy_url=row["proxy_url"] or "",
            notify_enabled=bool(row["notify_enabled"]),
            polling_enabled=bool(row["polling_enabled"]),
            sort_order=int(row["sort_order"]),
            allowed_provider=row["allowed_provider"] or "",
        )
        for row in rows
    ]


def update_group(
    settings: Settings,
    user_id: int,
    group_id: int,
    name: str,
    color: str,
    proxy_url: str = "",
    notify_enabled: bool | None = None,
    polling_enabled: bool | None = None,
    allowed_provider: str | None = None,
) -> Group | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            UPDATE groups
            SET name = ?, color = ?, proxy_url = ?,
                notify_enabled = COALESCE(?, notify_enabled),
                polling_enabled = COALESCE(?, polling_enabled),
                allowed_provider = COALESCE(?, allowed_provider)
            WHERE id = ? AND user_id = ?
            RETURNING id, name, color, proxy_url, notify_enabled, polling_enabled, sort_order,
                      allowed_provider
            """,
            (
                name,
                color,
                proxy_url,
                None if notify_enabled is None else int(notify_enabled),
                None if polling_enabled is None else int(polling_enabled),
                None if allowed_provider is None else (allowed_provider or ""),
                group_id,
                user_id,
            ),
        ).fetchone()
    if row is None:
        return None
    return Group(
        id=row["id"],
        name=row["name"],
        color=row["color"],
        proxy_url=row["proxy_url"] or "",
        notify_enabled=bool(row["notify_enabled"]),
        polling_enabled=bool(row["polling_enabled"]),
        sort_order=int(row["sort_order"]),
        allowed_provider=row["allowed_provider"] or "",
    )


def reorder_groups(settings: Settings, user_id: int, ordered_ids: list[int]) -> bool:
    """Persist a new display order for the user's groups.

    The request must contain exactly the user's own group ids (no duplicates,
    no foreign ids), otherwise nothing is written and False is returned.
    """
    with connect(settings) as connection:
        owned_rows = connection.execute(
            "SELECT id FROM groups WHERE user_id = ?", (user_id,)
        ).fetchall()
        owned_ids: set[int] = {int(row["id"]) for row in owned_rows}
        if len(owned_ids) != len(ordered_ids) or set(ordered_ids) != owned_ids:
            return False
        connection.executemany(
            "UPDATE groups SET sort_order = ? WHERE id = ? AND user_id = ?",
            [(index, group_id, user_id) for index, group_id in enumerate(ordered_ids)],
        )
    return True


def delete_groups(settings: Settings, user_id: int, group_ids: list[int]) -> int:
    """Delete several groups at once; returns the number of rows removed."""
    unique_ids: list[int] = list(dict.fromkeys(group_ids))
    if not unique_ids:
        return 0
    placeholders: str = ",".join("?" for _ in unique_ids)
    with connect(settings) as connection:
        result = connection.execute(
            f"DELETE FROM groups WHERE user_id = ? AND id IN ({placeholders})",
            (user_id, *unique_ids),
        )
    return int(result.rowcount)


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
