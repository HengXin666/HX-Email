"""Cursor boundary probes shared by the reader: newest id, oldest id, ahead check.

Split out of ``reader.py`` to keep both files under the 300 line ceiling; the query
builder and the scope types stay there, this module only measures the stored id range.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from hx_email.server.router.cursor import Cursor, ensure_not_ahead

if TYPE_CHECKING:
    from hx_email.server.router.impl.reader import Source

# 与 reader 的 id 边界一致; 在两处各写一份是为了避开 reader <-> bounds 的循环导入,
# reader 提供查询构造, bounds 只量 id 范围.
BOUNDARY: int = 0
COLUMNS: str = (
    "id, instance_id, direction, chat_id, chat_type, sender_id, sender_name, text, "
    "reply_to, message_id, attachments_json, occurred_at, raw_json, raw_ref, is_self, "
    "created_at, dedup_key"
)


def ensure_no_gap_ahead(
    connection: sqlite3.Connection, scope: Source, owned: list[int], start: int
) -> None:
    """A cursor past the newest stored id means the caller mixed up instances."""
    newest: int | None = newest_id(connection, scope, owned)
    ensure_not_ahead(Cursor(scope.instance_id or 0, start), newest or 0)


# 与 reader.py 互相导入: 这里只在 TYPE_CHECKING 与函数体内 import reader, 不要提到模块顶层
# 决策记录: .agents/notes/implemented/feature/2026-11-03-qq-live-wiring-fixes.md
def newest_id(connection: sqlite3.Connection, scope: Source, owned: list[int]) -> int | None:
    from hx_email.server.router.impl.reader import build_query

    probe, params = build_query(scope, owned, BOUNDARY - 1, "both", 1)
    sql: str = probe.replace(COLUMNS, "MAX(id) AS newest").replace("ORDER BY id ASC LIMIT ?", "")
    row: sqlite3.Row | None = connection.execute(sql, params[:-1]).fetchone()
    if row is None or row["newest"] is None:
        return None
    return int(row["newest"])


def oldest_id(connection: sqlite3.Connection, scope: Source, owned: list[int]) -> int | None:
    from hx_email.server.router.impl.reader import build_query

    probe, params = build_query(scope, owned, BOUNDARY - 1, "both", 1)
    sql: str = probe.replace(COLUMNS, "MIN(id) AS oldest").replace("ORDER BY id ASC LIMIT ?", "")
    row: sqlite3.Row | None = connection.execute(sql, params[:-1]).fetchone()
    if row is None or row["oldest"] is None:
        return None
    return int(row["oldest"])
