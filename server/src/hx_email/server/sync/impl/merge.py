"""Merge a snapshot database into a live instance without duplicates or loss."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from hx_email.config import Settings


class SyncMergeError(RuntimeError):
    """Raised when a snapshot cannot be merged into the live database."""


def load_rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


def inserted_id(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise SyncMergeError("SQLite did not return an inserted row id")
    return cursor.lastrowid


def strict_remap(mapping: dict[int, int], value: object) -> int:
    try:
        mapped: int | None = mapping.get(int(str(value)))
    except (TypeError, ValueError) as error:
        raise SyncMergeError(f"Snapshot contains an invalid row id: {value!r}") from error
    if mapped is None:
        raise SyncMergeError(f"Snapshot references a missing row id: {value!r}")
    return mapped


def optional_remap(mapping: dict[int, int], value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return strict_remap(mapping, value)


def merge_users(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
    overwrite: bool = True,
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for row in rows:
        existing = connection.execute(
            "SELECT id FROM users WHERE username = ?", (row["username"],)
        ).fetchone()
        if existing is not None:
            if overwrite:
                connection.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (row["password_hash"], existing[0]),
                )
            ids[int(row["id"])] = int(existing[0])
        else:
            # 快照中的 is_admin 不可信: 新用户一律非管理员, 防止持 sync key
            # 推送自造快照注入/提升管理员 (第五轮审计 #4)。
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 0)",
                (row["username"], row["password_hash"]),
            )
            ids[int(row["id"])] = inserted_id(cursor)
    return ids


def merge_system_settings(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
    overwrite: bool = True,
) -> None:
    for row in rows:
        if overwrite:
            connection.execute(
                "INSERT INTO system_settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (row["key"], row["value"]),
            )
        else:
            connection.execute(
                "INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)",
                (row["key"], row["value"]),
            )


def merge_snapshot(
    connection: sqlite3.Connection,
    settings: Settings,
    snapshot_path: Path,
    overwrite: bool = True,
) -> dict[str, int]:
    from hx_email.server.sync.impl.merge_entities import (
        merge_email_accounts,
        merge_groups,
        merge_platform_bindings,
        merge_platforms,
        merge_tags,
        merge_usable_email_tags,
        merge_usable_emails,
    )
    from hx_email.server.sync.impl.merge_mailbox import (
        merge_fetched_messages,
        merge_mail_pool_entries,
        merge_temp_mailboxes,
        merge_verification_readings,
    )

    with sqlite3.connect(snapshot_path) as source:
        source.row_factory = sqlite3.Row
        user_ids: dict[int, int] = merge_users(
            connection, load_rows(source, "users"), overwrite=overwrite
        )
        # push (overwrite=False) 不合并 system_settings: 快照可携带 external_api_key
        # 等密钥类设置, 直接写入会植入凭证 (第五轮审计 #4)。pull 方向仍同步设置。
        if overwrite:
            merge_system_settings(
                connection, load_rows(source, "system_settings"), overwrite=overwrite
            )
        group_ids: dict[int, int] = merge_groups(
            connection, user_ids, load_rows(source, "groups"), overwrite=overwrite
        )
        tag_ids: dict[int, int] = merge_tags(
            connection, user_ids, load_rows(source, "tags"), overwrite=overwrite
        )
        account_ids: dict[int, int] = merge_email_accounts(
            settings,
            connection,
            user_ids,
            group_ids,
            load_rows(source, "email_accounts"),
            overwrite=overwrite,
        )
        email_ids: dict[int, int] = merge_usable_emails(
            connection,
            user_ids,
            account_ids,
            group_ids,
            load_rows(source, "usable_emails"),
            overwrite=overwrite,
        )
        merge_usable_email_tags(
            connection, email_ids, tag_ids, load_rows(source, "usable_email_tags")
        )
        platform_ids: dict[int, int] = merge_platforms(
            connection, user_ids, load_rows(source, "platforms")
        )
        merge_platform_bindings(
            connection,
            user_ids,
            email_ids,
            platform_ids,
            load_rows(source, "platform_bindings"),
            overwrite=overwrite,
        )
        merge_temp_mailboxes(
            connection,
            user_ids,
            email_ids,
            load_rows(source, "temp_mailboxes"),
            overwrite=overwrite,
        )
        merge_mail_pool_entries(
            connection,
            user_ids,
            email_ids,
            load_rows(source, "mail_pool_entries"),
            overwrite=overwrite,
        )
        merge_verification_readings(
            connection, user_ids, email_ids, load_rows(source, "verification_readings")
        )
        merge_fetched_messages(
            connection,
            user_ids,
            email_ids,
            account_ids,
            load_rows(source, "fetched_messages"),
        )
    table_names: tuple[str, ...] = (
        "users",
        "system_settings",
        "groups",
        "tags",
        "email_accounts",
        "usable_emails",
        "usable_email_tags",
        "platforms",
        "platform_bindings",
        "temp_mailboxes",
        "mail_pool_entries",
        "verification_readings",
        "fetched_messages",
    )
    return {name: len(load_rows(connection, name)) for name in table_names}
