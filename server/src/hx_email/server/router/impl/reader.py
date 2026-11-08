"""Cursor-based incremental reads over ``messaging_messages`` (spec section 7).

Every read is ``WHERE id > ? ORDER BY id LIMIT n`` against the existing
``(instance_id, chat_id, id)`` index. No OFFSET, no full scan: the point of the cursor
is that a slow consumer never re-reads what it acknowledged and never skips what
arrived while it was away.

``parse_source`` turns ``source`` into a scope that narrows the SQL: v1 ``qq:``,
``qq:3:``, ``qq:3:group:``, a full v1 address, or any v2 address or selector.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.contract.address import AddressError, LegacyScope, is_v2, parse_address
from hx_email.server.contract.address import legacy_scope as v2_scope
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.router.bounds import ensure_no_gap_ahead, oldest_id
from hx_email.server.router.cursor import (
    Cursor,
    decode_cursor,
    encode_cursor,
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
PLATFORMS = REGISTRY.platform_names()
# 旧写入路径只存纯号, 补地址时要一个平台名; messaging_instances.kind 到这里只有 qq.
PLATFORM_OF_KIND: str = "qq"
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
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadPage:
    """One page of envelopes plus where to resume and whether more is waiting."""

    messages: list[Envelope]
    next_cursor: str
    has_more: bool
    gap: bool = False


# v2 选择器翻译成 v1 精确值加 LIKE 模式, 仓库级前缀靠 patterns
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-contract-v2.md
def parse_source(source: str) -> Source:
    """Accept ``qq:``, ``qq:3:``, ``qq:3:group:``, a full v1 address, or v2."""
    if is_v2(source):
        try:
            scope: LegacyScope = v2_scope(parse_address(source))
        except AddressError as error:
            raise SessionNotFoundError(str(error)) from error
        return Source(scope.platform, scope.instance_id, None, scope.exact or None, scope.patterns)
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


def peer_of(address: str) -> str:
    """Peer id from a full address; a bare id comes back unchanged."""
    parts: list[str] = address.split(":")
    return parts[3] if len(parts) >= 4 else address


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
    if scope.patterns:
        likes: list[str] = ["chat_id LIKE ? ESCAPE '\\'" for _ in scope.patterns]
        clauses.append("(" + " OR ".join(["chat_id = ?", *likes]) + ")")
        params.extend([scope.chat_id or "", *scope.patterns])
    elif scope.chat_id:
        # 两条写入路径的 chat_id 格式不同: 事件端点 (messaging/store.save_message) 存纯号,
        # 路由层 (router/impl/store.store_inbound) 存完整地址. 两种都认, 否则同一个会话
        # 会因为写入方不同而查不到.
        clauses.append("(chat_id = ? OR chat_id = ?)")
        params.append(scope.chat_id)
        params.append(peer_of(scope.chat_id))
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
    return max(1, min(limit, MAX_LIMIT))


def _attachments(raw: str) -> tuple[Attachment, ...]:
    """Decode the stored attachment list; a malformed value yields none rather than an error."""
    if not raw:
        return ()
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        return ()
    if not isinstance(parsed, list):
        return ()
    out: list[Attachment] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        size_value: object = item.get("size") or 0
        out.append(
            Attachment(
                kind=str(item.get("kind") or ""),
                url=str(item.get("url") or ""),
                name=str(item.get("name") or ""),
                size=size_value if isinstance(size_value, int) else 0,
            )
        )
    return tuple(out)


def _row_to_envelope(settings: Settings, row: sqlite3.Row, include_raw: bool) -> Envelope:
    message_id: int = int(row["id"])
    instance_id: int = int(row["instance_id"])
    chat_id: str = str(row["chat_id"])
    if ":" not in chat_id:
        # 旧写入路径存的是纯号, 补齐成完整地址再解析, 否则整页都读不出来.
        stored_type: str = str(row["chat_type"] or "private")
        chat_id = f"{PLATFORM_OF_KIND}:{instance_id}:{stored_type}:{chat_id}"
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
        attachments=_attachments(str(row["attachments_json"] or "")),
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
            _row_to_envelope(settings, row, include_raw) for row in page_rows
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
