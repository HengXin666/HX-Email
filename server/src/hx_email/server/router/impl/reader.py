"""Cursor-based incremental reads over ``messaging_messages`` (spec section 7).

Every read is ``WHERE id > ? ORDER BY id LIMIT n`` against the existing
``(instance_id, chat_id, id)`` index. No OFFSET, no full scan: the point of the cursor
is that a slow consumer never re-reads what it acknowledged and never skips what
arrived while it was away.

``parse_source`` turns the ``source`` a tool call receives into a scope. Four shapes
are allowed, and each one narrows the query rather than filtering in Python:
``qq:`` (whole platform), ``qq:3:`` (one instance), ``qq:3:group:`` (one chat type),
``qq:3:group:1`` (one session).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.router.cursor import (
    Cursor,
    decode_cursor,
    encode_cursor,
    ensure_not_ahead,
    ensure_scope,
    has_gap,
)
from hx_email.server.router.envelope import (
    Attachment,
    Envelope,
    Sender,
    iso_utc_from_sqlite,
    parse_session,
)
from hx_email.server.router.errors import CursorInvalidError, SessionNotFoundError
from hx_email.server.router.impl.store import read_raw

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
BOUNDARY = 0
MAX_STORED_POSITION = 2**31 - 1
PLATFORMS = ("qq", "github")
COLUMNS = (
    "id, instance_id, direction, chat_id, chat_type, sender_id, sender_name, text, "
    "reply_to, message_id, attachments_json, occurred_at, raw_json, raw_ref, is_self, "
    "created_at, dedup_key"
)


@dataclass(frozen=True)
class Source:
    """A narrowed read scope; None means "do not filter on this field"."""

    platform: str
    instance_id: int | None = None
    session_type: str | None = None
    chat_id: str | None = None


@dataclass(frozen=True)
class ReadPage:
    """One page of envelopes plus where to resume and whether more is waiting."""

    messages: list[Envelope]
    next_cursor: str
    has_more: bool
    gap: bool = False


def parse_source(source: str) -> Source:
    """Accept ``qq:``, ``qq:3:``, ``qq:3:group:`` or a full session address."""
    parts: list[str] = source.split(":")
    platform: str = parts[0]
    if platform not in PLATFORMS:
        raise SessionNotFoundError(f"unknown platform in source: {source!r}")
    if len(parts) == 2 and parts[1] == "":
        return Source(platform)
    if len(parts) < 3 or not parts[1].isdigit():
        raise SessionNotFoundError(f"cannot parse source: {source!r}")
    instance_id: int = int(parts[1])
    if instance_id <= 0:
        raise SessionNotFoundError(f"instance id must be positive: {source!r}")
    rest: list[str] = parts[2:]
    if rest == [""]:
        return Source(platform, instance_id)
    if len(rest) == 2 and rest[1] == "":
        return Source(platform, instance_id, session_type=rest[0])
    try:
        address = parse_session(source)
    except SessionNotFoundError as error:
        raise SessionNotFoundError(str(error)) from error
    return Source(platform, instance_id, session_type=address.session_type, chat_id=source)


def build_query(
    scope: Source, instance_ids: list[int], start: int, direction: str, limit: int
) -> tuple[str, list[object]]:
    """Build the parameterised page query; a single-session read hits the index."""
    clauses: list[str] = []
    params: list[object] = []
    if scope.instance_id is not None:
        clauses.append("instance_id = ?")
        params.append(scope.instance_id)
    elif instance_ids:
        placeholders: str = ", ".join("?" for _ in instance_ids)
        clauses.append(f"instance_id IN ({placeholders})")
        params.extend(instance_ids)
    else:
        clauses.append("1 = 0")
    if scope.chat_id:
        clauses.append("chat_id = ?")
        params.append(scope.chat_id)
    elif scope.session_type:
        clauses.append("chat_id LIKE ?")
        params.append(f"{scope.platform}:%:{scope.session_type}:%")
    if direction != "both":
        clauses.append("direction = ?")
        params.append(direction)
    clauses.append("id > ?")
    params.append(start)
    sql: str = (
        f"SELECT {COLUMNS} FROM messaging_messages WHERE "
        + " AND ".join(clauses)
        + " ORDER BY id ASC LIMIT ?"
    )
    params.append(limit + 1)
    return sql, params


def _clamp(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_LIMIT)


def _attachment_items(raw: str) -> tuple[dict[str, object], ...]:
    if not raw:
        return ()
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(item for item in parsed if isinstance(item, dict))


def _to_attachment(item: dict[str, object]) -> Attachment:
    size_value: object = item.get("size") or 0
    return Attachment(
        kind=str(item.get("kind") or ""),
        url=str(item.get("url") or ""),
        name=str(item.get("name") or ""),
        size=size_value if isinstance(size_value, int) else 0,
    )


def _row_to_envelope(settings: Settings, row: sqlite3.Row, include_raw: bool) -> Envelope:
    message_id: int = int(row["id"])
    instance_id: int = int(row["instance_id"])
    chat_id: str = str(row["chat_id"])
    address = parse_session(chat_id)
    raw: dict[str, object] | None = None
    if include_raw:
        raw = read_raw(
            settings,
            instance_id,
            message_id,
            str(row["raw_json"] or ""),
            str(row["raw_ref"] or ""),
        )
    return Envelope(
        id=f"m_{message_id}",
        cursor=encode_cursor(instance_id, message_id),
        platform=address.platform,
        instance_id=instance_id,
        session=chat_id,
        session_type=address.session_type,
        direction=str(row["direction"]),
        sender=Sender(
            id=str(row["sender_id"] or ""),
            name=str(row["sender_name"] or ""),
            is_self=bool(row["is_self"]),
        ),
        text=str(row["text"] or ""),
        reply_to=str(row["reply_to"] or ""),
        platform_message_id=str(row["message_id"] or ""),
        attachments=tuple(
            _to_attachment(item) for item in _attachment_items(str(row["attachments_json"] or ""))
        ),
        occurred_at=str(row["occurred_at"] or row["created_at"] or ""),
        received_at=iso_utc_from_sqlite(str(row["created_at"] or "")),
        raw=raw,
        raw_ref=str(row["raw_ref"] or ""),
    )


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
        _ensure_not_ahead(connection, scope, owned, start)
        sql, params = build_query(scope, owned, start, direction, size)
        rows: list[sqlite3.Row] = connection.execute(sql, params).fetchall()
        has_more: bool = len(rows) > size
        page_rows: list[sqlite3.Row] = rows[:size]
        messages: list[Envelope] = [
            _row_to_envelope(settings, row, include_raw) for row in page_rows
        ]
        position: int = int(page_rows[-1]["id"]) if page_rows else start
        oldest: int | None = _oldest(connection, scope, owned)
    return ReadPage(
        messages=messages,
        next_cursor=encode_cursor(cursor_instance, position),
        has_more=has_more,
        gap=has_gap(Cursor(cursor_instance, start), oldest),
    )


def _ensure_not_ahead(
    connection: sqlite3.Connection, scope: Source, owned: list[int], start: int
) -> None:
    """A cursor past the newest stored id means the caller mixed up instances."""
    newest: int | None = _newest(connection, scope, owned)
    ensure_not_ahead(Cursor(scope.instance_id or 0, start), newest or 0)


def _newest(connection: sqlite3.Connection, scope: Source, owned: list[int]) -> int | None:
    probe, params = build_query(scope, owned, BOUNDARY - 1, "both", 1)
    sql: str = probe.replace(COLUMNS, "MAX(id) AS newest").replace("ORDER BY id ASC LIMIT ?", "")
    row: sqlite3.Row | None = connection.execute(sql, params[:-1]).fetchone()
    if row is None or row["newest"] is None:
        return None
    return int(row["newest"])


def _oldest(connection: sqlite3.Connection, scope: Source, owned: list[int]) -> int | None:
    probe, params = build_query(scope, owned, BOUNDARY - 1, "both", 1)
    sql: str = probe.replace(COLUMNS, "MIN(id) AS oldest").replace("ORDER BY id ASC LIMIT ?", "")
    row: sqlite3.Row | None = connection.execute(sql, params[:-1]).fetchone()
    if row is None or row["oldest"] is None:
        return None
    return int(row["oldest"])


def latest_cursor(settings: Settings, instance_id: int) -> str:
    """Cursor pointing after the newest stored message of one instance."""
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT MAX(id) AS newest FROM messaging_messages WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()
    newest: int = int(row["newest"]) if row is not None and row["newest"] else BOUNDARY
    return encode_cursor(instance_id, newest)
