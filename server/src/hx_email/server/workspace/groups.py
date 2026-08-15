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
) -> Group:
    if not proxy_url:
        proxy_url = get_setting(settings, "group_default_proxy_url", "")
    if notify_enabled is None:
        notify_enabled = get_setting(settings, "group_default_notify_enabled", "true") == "true"
    if polling_enabled is None:
        polling_enabled = get_setting(settings, "group_default_polling_enabled", "true") == "true"
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO groups (user_id, name, color, proxy_url, notify_enabled, polling_enabled)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, name, color, proxy_url, int(notify_enabled), int(polling_enabled)),
        )
    return Group(
        id=require_inserted_id(cursor.lastrowid),
        name=name,
        color=color,
        proxy_url=proxy_url,
        notify_enabled=notify_enabled,
        polling_enabled=polling_enabled,
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
            "INSERT INTO groups (user_id, name, color, proxy_url, notify_enabled, polling_enabled)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                user_id,
                group["name"],
                group.get("color", "#58a6ff"),
                group.get("proxy_url") or default_proxy_url,
                int(coerce_bool(group.get("notify_enabled"), default_notify)),
                int(coerce_bool(group.get("polling_enabled"), default_polling)),
            ),
        )
        ids[int(group["id"])] = require_inserted_id(cursor.lastrowid)
    return ids


def list_groups(settings: Settings, user_id: int) -> list[Group]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT id, name, color, proxy_url, notify_enabled, polling_enabled FROM groups"
            " WHERE user_id = ? ORDER BY id",
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
) -> Group | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            UPDATE groups
            SET name = ?, color = ?, proxy_url = ?,
                notify_enabled = COALESCE(?, notify_enabled),
                polling_enabled = COALESCE(?, polling_enabled)
            WHERE id = ? AND user_id = ?
            RETURNING id, name, color, proxy_url, notify_enabled, polling_enabled
            """,
            (
                name,
                color,
                proxy_url,
                None if notify_enabled is None else int(notify_enabled),
                None if polling_enabled is None else int(polling_enabled),
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
    )


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


def export_group_accounts_text(settings: Settings, user_id: int, group_id: int) -> str | None:
    """Export email accounts in a group as tab-separated text."""
    with connect(settings) as connection:
        group_row = connection.execute(
            "SELECT id, name FROM groups WHERE id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        if group_row is None:
            return None

        rows = connection.execute(
            """
            SELECT ea.primary_address, ea.provider, ea.display_name, ea.status
            FROM email_accounts ea
            INNER JOIN usable_emails ue
              ON ue.email_account_id = ea.id AND ue.user_id = ea.user_id
            WHERE ea.user_id = ? AND ue.group_id = ?
            ORDER BY ea.id
            """,
            (user_id, group_id),
        ).fetchall()

    lines: list[str] = [
        f"# Group: {group_row['name']}",
        "# Email\tProvider\tDisplay Name\tStatus",
    ]
    for row in rows:
        lines.append(
            "\t".join(
                [
                    row["primary_address"],
                    row["provider"],
                    row["display_name"],
                    row["status"],
                ]
            )
        )
    return "\n".join(lines)
