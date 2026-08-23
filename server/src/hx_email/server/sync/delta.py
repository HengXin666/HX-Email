"""Incremental sync: WAL-driven change transfer with periodic full baselines.

PG 风格设计: sync_changelog 是数据库的变更日志 (WAL), 常规同步只传输
自上次水位以来的变更行 (增量包), 由接收方复用 merge_snapshot 的自然键
upsert + id remap 合并; 只有超过 sync_full_interval_seconds 才做一次全量
快照作为基线纠偏。全量路径 (pull_snapshot/push_snapshot) 保持不变。

增量方向:
  - pull: GET /api/v1/admin/sync/delta?after=<seq> -> 主实例返回变更集
  - push: POST /api/v1/admin/sync/delta -> 从实例推送本地变更集
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.instance_backup.archive import DATABASE_NAME
from hx_email.server.sync.impl.merge import (
    max_changelog_seq,
    merge_snapshot,
    reference_table,
    row_dict,
)
from hx_email.server.sync.watermark import SyncWatermark

MAX_DELTA_ROWS: int = 2000

# changelog 表 -> 该表行被合并时需要同批携带的"父表"引用列。
# 增量包按父表补充这些引用的行, 保证 merge 的 strict_remap 不会失败。
REFERENCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "users": (),
    "groups": ("user_id",),
    "tags": ("user_id",),
    "email_accounts": ("user_id", "group_id"),
    "usable_emails": ("user_id", "email_account_id", "group_id"),
    "usable_email_tags": ("usable_email_id", "tag_id"),
    "platforms": ("user_id",),
    "platform_bindings": ("user_id", "usable_email_id", "platform_id"),
    "temp_mailboxes": ("user_id", "usable_email_id"),
    "mail_pool_entries": ("user_id", "usable_email_id"),
    "verification_readings": ("user_id", "usable_email_id"),
    "fetched_messages": ("user_id", "usable_email_id", "email_account_id"),
}

# merge_snapshot 按序合并的表 (与 merge.py 中顺序一致), 用于构建增量快照。
# system_settings / usable_email_tags 无整数主键不进 changelog, 但快照库仍需
# 建表 (merge 会 load 它们), 故保留在顺序中。
MERGE_ORDER: tuple[str, ...] = (
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


def build_delta_rows(settings: Settings, after_seq: int) -> dict[str, dict[int, dict[str, Any]]]:
    """Read changelog rows after `after_seq` and expand referenced parents.

    Returns a {table: {row_id: row_dict}} map, newest-first capped by
    MAX_DELTA_ROWS total rows. The change set is self-contained: referenced
    parent rows are appended recursively so merge_snapshot can resolve FKs.
    """
    rows: dict[str, dict[int, dict[str, Any]]] = {}
    with connect(settings) as connection:
        changelog_rows = connection.execute(
            "SELECT table_name, row_id FROM sync_changelog WHERE id > ? ORDER BY id LIMIT ?",
            (after_seq, MAX_DELTA_ROWS),
        ).fetchall()
        for entry in changelog_rows:
            table: str = str(entry["table_name"])
            row_id: int = int(entry["row_id"])
            current: dict[str, Any] | None = row_dict(connection, table, row_id)
            if current is None:
                continue
            rows.setdefault(table, {})[row_id] = current
        collect_references(connection, rows)
    return rows


def build_delta_package(
    settings: Settings,
    watermark: SyncWatermark,
) -> tuple[dict[str, Any], SyncWatermark]:
    """Serialise the local change set since the last pushed watermark.

    The payload carries the local changelog high-water mark in `seq` so the
    peer can advance its pull watermark exactly to what this package covered.
    """
    rows: dict[str, dict[int, dict[str, Any]]] = build_delta_rows(settings, watermark.last_push_seq)
    table_payload: dict[str, list[dict[str, Any]]] = {
        table: list(by_id.values()) for table, by_id in rows.items()
    }
    next_seq: int = max_changelog_seq(settings)
    payload: dict[str, Any] = {"tables": table_payload, "seq": next_seq}
    return payload, SyncWatermark(
        last_pull_seq=watermark.last_pull_seq,
        last_push_seq=max(watermark.last_push_seq, next_seq),
        last_full_at=watermark.last_full_at,
    )


def apply_delta_package(
    settings: Settings,
    payload: dict[str, Any],
) -> dict[str, int]:
    """Apply a delta package by merging its rows through the snapshot path."""
    tables_raw: object = payload.get("tables")
    if not isinstance(tables_raw, dict):
        raise ValueError("Delta package is missing tables")
    tables: dict[str, Any] = tables_raw
    row_count: int = sum(len(rows) for rows in tables.values() if isinstance(rows, list))
    if row_count == 0:
        return {}
    with tempfile.TemporaryDirectory(prefix="hx-email-delta-") as temp_name:
        staging_dir: Path = Path(temp_name)
        snapshot_path: Path = staging_dir / DATABASE_NAME
        write_snapshot_database(settings, tables, snapshot_path)
        with connect(settings) as connection:
            connection.execute("INSERT OR REPLACE INTO sync_suppress (id, active) VALUES (1, 1)")
            try:
                counts: dict[str, int] = merge_snapshot(
                    connection, settings, snapshot_path, overwrite=True
                )
            finally:
                connection.execute("UPDATE sync_suppress SET active = 0 WHERE id = 1")
        return counts


def collect_references(
    connection: sqlite3.Connection,
    rows: dict[str, dict[int, dict[str, Any]]],
) -> None:
    """Expand a change set with referenced parent rows (closure over FKs)."""
    pending: list[tuple[str, int]] = [
        (table, row_id) for table, by_id in rows.items() for row_id in by_id
    ]
    seen: set[tuple[str, int]] = set(pending)
    while pending:
        table, row_id = pending.pop()
        current: dict[str, Any] | None = rows.get(table, {}).get(row_id)
        if current is None:
            continue
        for column in REFERENCE_COLUMNS.get(table, ()):
            ref_value: object = current.get(column)
            if ref_value is None:
                continue
            ref_table: str = reference_table(column)
            ref_id: int = int(str(ref_value))
            if (ref_table, ref_id) in seen:
                continue
            parent: dict[str, Any] | None = row_dict(connection, ref_table, ref_id)
            if parent is None:
                continue
            rows.setdefault(ref_table, {})[ref_id] = parent
            seen.add((ref_table, ref_id))
            pending.append((ref_table, ref_id))


def write_snapshot_database(
    settings: Settings,
    tables: dict[str, Any],
    target: Path,
) -> None:
    """Create a minimal database file containing only the delta rows."""
    with connect(settings) as source, sqlite3.connect(target) as target_conn:
        for table in MERGE_ORDER:
            copy_table_structure(source, target_conn, table)
            rows: object = tables.get(table)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                insert_row(target_conn, table, row)


def copy_table_structure(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    table: str,
) -> None:
    columns: list[str] = [
        str(row[1]) for row in source.execute(f"PRAGMA table_info({table})").fetchall()
    ]
    if not columns:
        return
    column_sql: str = ", ".join(f'"{name}"' for name in columns)
    target.execute(f'CREATE TABLE "{table}" ({column_sql})')


def insert_row(
    connection: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
) -> None:
    columns: list[str] = list(row.keys())
    if not columns:
        return
    placeholders: str = ", ".join("?" for _ in columns)
    quoted: str = ", ".join(f'"{name}"' for name in columns)
    connection.execute(
        f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})',
        tuple(row.get(name) for name in columns),
    )
