"""Cursor-based incremental reads over ``messaging_messages`` (spec section 7).

Every read is ``WHERE id > ? ORDER BY id LIMIT n`` against the existing
``(instance_id, chat_id, id)`` index. No OFFSET, no full scan: the point of the cursor
is that a slow consumer never re-reads what it acknowledged and never skips what
arrived while it was away.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.router.bounds import ensure_no_gap_ahead, oldest_id
from hx_email.server.router.cursor import (
    Cursor,
    decode_cursor,
    encode_cursor,
    ensure_scope,
    has_gap,
)
from hx_email.server.router.envelope import Envelope
from hx_email.server.router.errors import CursorInvalidError, SessionNotFoundError
from hx_email.server.router.impl.reader.rows import row_to_envelope
from hx_email.server.router.impl.reader.source import Source, build_query, parse_source

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
BOUNDARY = 0
MAX_STORED_POSITION = 2**31 - 1


@dataclass(frozen=True)
class ReadPage:
    """One page of envelopes plus where to resume and whether more is waiting."""

    messages: list[Envelope]
    next_cursor: str
    has_more: bool
    gap: bool = False


def _clamp(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def owned_instances(connection: sqlite3.Connection, user_id: int) -> list[int]:
    """Instances the caller may read; a foreign id is a 404 rather than an empty page."""
    rows: list[sqlite3.Row] = connection.execute(
        "SELECT id FROM messaging_instances WHERE user_id = ? ORDER BY id", (user_id,)
    ).fetchall()
    return [int(row["id"]) for row in rows]


def _start_position(scope: Source, cursor: str, owned: list[int]) -> tuple[int, int]:
    """Return (position, cursor_instance_id) after validating the cursor's scope."""
    if not cursor:
        return BOUNDARY, scope.instance_id or BOUNDARY
    parsed: Cursor = decode_cursor(cursor)
    if scope.instance_id is not None:
        ensure_scope(parsed, scope.instance_id)
        return parsed.position, scope.instance_id

    if parsed.position and parsed.instance_id not in owned and parsed.instance_id != 0:
        raise CursorInvalidError(f"cursor belongs to instance {parsed.instance_id}")
    return parsed.position, parsed.instance_id


# chat_id 纯号与完整地址两种格式并存, 查询两种都认; 边界探测在 bounds.py, 两边有循环导入
# 决策记录: .agents/notes/implemented/feature/2026-11-03-qq-live-wiring-fixes.md
def read_messages(
    settings: Settings,
    user_id: int,
    source: str,
    cursor: str,
    *,
    limit: int = DEFAULT_LIMIT,
    direction: str = "inbound",
    include_raw: bool = False,
) -> ReadPage:
    """Read messages newer than ``cursor`` within ``source``."""
    scope: Source = parse_source(source)
    size: int = _clamp(limit)
    with connect(settings) as connection:
        owned: list[int] = owned_instances(connection, user_id)
        if scope.instance_id is not None and scope.instance_id not in owned:
            raise SessionNotFoundError(f"instance {scope.instance_id} is not yours")
        start, cursor_instance = _start_position(scope, cursor, owned)
        if scope.instance_id is None and start and not owned:
            raise CursorInvalidError("no instance is readable for this account")
        ensure_no_gap_ahead(connection, scope, owned, start)
        sql, params = build_query(scope, owned, start, direction, size)
        rows: list[sqlite3.Row] = connection.execute(sql, params).fetchall()
        has_more: bool = len(rows) > size
        page_rows: list[sqlite3.Row] = rows[:size]
        messages: list[Envelope] = [
            row_to_envelope(settings, row, include_raw) for row in page_rows
        ]
        position: int = int(page_rows[-1]["id"]) if page_rows else start
        oldest: int | None = oldest_id(connection, scope, owned)
    return ReadPage(
        messages=messages,
        next_cursor=encode_cursor(cursor_instance, position),
        has_more=has_more,
        gap=has_gap(Cursor(cursor_instance, start), oldest),
    )


def latest_cursor(settings: Settings, instance_id: int) -> str:
    """Cursor pointing after the newest stored message of one instance."""
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT MAX(id) AS newest FROM messaging_messages WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()
    newest: int = int(row["newest"]) if row is not None and row["newest"] else BOUNDARY
    return encode_cursor(instance_id, newest)
