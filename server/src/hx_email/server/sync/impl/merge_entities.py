"""Merge entity tables (accounts, emails, groups, tags, platforms)."""

from __future__ import annotations

import sqlite3
from typing import Any

from hx_email.config import Settings
from hx_email.database import utc_now_iso
from hx_email.security import encrypt_secret
from hx_email.server.sync.impl.merge import inserted_id, optional_remap, strict_remap


def merge_groups(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for row in rows:
        user_id: int = strict_remap(user_ids, row["user_id"])
        existing = connection.execute(
            "SELECT id FROM groups WHERE user_id = ? AND name = ?", (user_id, row["name"])
        ).fetchone()
        if existing is not None:
            connection.execute(
                "UPDATE groups SET color = ?, proxy_url = ?, notify_enabled = ?,"
                " polling_enabled = ? WHERE id = ?",
                (
                    row["color"],
                    row["proxy_url"],
                    int(bool(row["notify_enabled"])),
                    int(bool(row["polling_enabled"])),
                    existing[0],
                ),
            )
            ids[int(row["id"])] = int(existing[0])
        else:
            cursor = connection.execute(
                "INSERT INTO groups (user_id, name, color, proxy_url, notify_enabled,"
                " polling_enabled) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    row["name"],
                    row["color"],
                    row["proxy_url"],
                    int(bool(row["notify_enabled"])),
                    int(bool(row["polling_enabled"])),
                ),
            )
            ids[int(row["id"])] = inserted_id(cursor)
    return ids


def merge_tags(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for row in rows:
        user_id: int = strict_remap(user_ids, row["user_id"])
        existing = connection.execute(
            "SELECT id FROM tags WHERE user_id = ? AND name = ?", (user_id, row["name"])
        ).fetchone()
        if existing is not None:
            connection.execute(
                "UPDATE tags SET color = ? WHERE id = ?", (row["color"], existing[0])
            )
            ids[int(row["id"])] = int(existing[0])
        else:
            cursor = connection.execute(
                "INSERT INTO tags (user_id, name, color) VALUES (?, ?, ?)",
                (user_id, row["name"], row["color"]),
            )
            ids[int(row["id"])] = inserted_id(cursor)
    return ids


def merge_email_accounts(
    settings: Settings,
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    group_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for row in rows:
        user_id: int = strict_remap(user_ids, row["user_id"])
        group_id: int | None = optional_remap(group_ids, row["group_id"])
        encrypted_token: str = encrypt_secret(settings, str(row.get("refresh_token") or ""))
        existing = connection.execute(
            "SELECT id FROM email_accounts WHERE user_id = ? AND primary_address = ?",
            (user_id, row["primary_address"]),
        ).fetchone()
        values: tuple[object, ...] = (
            user_id,
            row["provider"],
            row["primary_address"],
            row["display_name"],
            row["imap_host"],
            row["imap_port"],
            row["username"],
            row["imap_password"],
            row["client_id"],
            encrypted_token,
            row["status"],
            group_id,
            row["remark"],
            int(bool(row["telegram_enabled"])),
            row.get("last_refresh_at"),
        )
        if existing is not None:
            connection.execute(
                "UPDATE email_accounts SET user_id = ?, provider = ?, primary_address = ?,"
                " display_name = ?, imap_host = ?, imap_port = ?, username = ?,"
                " imap_password = ?, client_id = ?, refresh_token = ?, status = ?,"
                " group_id = ?, remark = ?, telegram_enabled = ?, last_refresh_at = ?"
                " WHERE id = ?",
                (*values, existing[0]),
            )
            ids[int(row["id"])] = int(existing[0])
        else:
            cursor = connection.execute(
                "INSERT INTO email_accounts (user_id, provider, primary_address, display_name,"
                " imap_host, imap_port, username, imap_password, client_id, refresh_token,"
                " status, group_id, remark, telegram_enabled, last_refresh_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            ids[int(row["id"])] = inserted_id(cursor)
    return ids


def merge_usable_emails(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    account_ids: dict[int, int],
    group_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for row in rows:
        user_id: int = strict_remap(user_ids, row["user_id"])
        account_id: int | None = optional_remap(account_ids, row["email_account_id"])
        group_id: int | None = optional_remap(group_ids, row["group_id"])
        existing = connection.execute(
            "SELECT id FROM usable_emails WHERE user_id = ? AND address = ?",
            (user_id, row["address"]),
        ).fetchone()
        values: tuple[object, ...] = (
            user_id,
            account_id,
            row["address"],
            row["label"],
            row["kind"],
            row["status"],
            int(bool(row["active"])),
            group_id,
            int(bool(row["notify_enabled"])),
            row.get("created_at") or utc_now_iso(),
        )
        if existing is not None:
            connection.execute(
                "UPDATE usable_emails SET user_id = ?, email_account_id = ?, address = ?,"
                " label = ?, kind = ?, status = ?, active = ?, group_id = ?,"
                " notify_enabled = ?, created_at = ? WHERE id = ?",
                (*values, existing[0]),
            )
            ids[int(row["id"])] = int(existing[0])
        else:
            cursor = connection.execute(
                "INSERT INTO usable_emails (user_id, email_account_id, address, label, kind,"
                " status, active, group_id, notify_enabled, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            ids[int(row["id"])] = inserted_id(cursor)
    return ids


def merge_usable_email_tags(
    connection: sqlite3.Connection,
    email_ids: dict[int, int],
    tag_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        connection.execute(
            "INSERT OR IGNORE INTO usable_email_tags (usable_email_id, tag_id) VALUES (?, ?)",
            (
                strict_remap(email_ids, row["usable_email_id"]),
                strict_remap(tag_ids, row["tag_id"]),
            ),
        )


def merge_platforms(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for row in rows:
        user_id: int = strict_remap(user_ids, row["user_id"])
        existing = connection.execute(
            "SELECT id FROM platforms WHERE user_id = ? AND name = ?", (user_id, row["name"])
        ).fetchone()
        if existing is not None:
            ids[int(row["id"])] = int(existing[0])
        else:
            cursor = connection.execute(
                "INSERT INTO platforms (user_id, name) VALUES (?, ?)", (user_id, row["name"])
            )
            ids[int(row["id"])] = inserted_id(cursor)
    return ids


def merge_platform_bindings(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    email_ids: dict[int, int],
    platform_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        user_id: int = strict_remap(user_ids, row["user_id"])
        email_id: int = strict_remap(email_ids, row["usable_email_id"])
        platform_id: int = strict_remap(platform_ids, row["platform_id"])
        existing = connection.execute(
            "SELECT id FROM platform_bindings WHERE user_id = ? AND usable_email_id = ?"
            " AND platform_id = ?",
            (user_id, email_id, platform_id),
        ).fetchone()
        if existing is not None:
            connection.execute(
                "UPDATE platform_bindings SET status = ?, notes = ? WHERE id = ?",
                (row["status"], row["notes"], existing[0]),
            )
        else:
            connection.execute(
                "INSERT INTO platform_bindings (user_id, usable_email_id, platform_id,"
                " status, notes) VALUES (?, ?, ?, ?, ?)",
                (user_id, email_id, platform_id, row["status"], row["notes"]),
            )
