"""Router table reads and writes: transactions, inbound rows, outbox rows (spec 7, 10).

Inbound rows land in ``messaging_messages`` with the permanent ``(instance_id, dedup_key)``
unique index doing the dedup. One message is one short transaction. Raw payloads above
16 KB go to ``router_raw/...`` (spec 10.3): the file is written before the row commits and
removed again when the commit fails.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.router.envelope import (
    InboundMessage,
    attachment_to_dict,
    encode_raw,
    needs_offload,
    raw_relative_path,
    write_raw_file,
)

TIME_FORMAT: str = "%Y-%m-%d %H:%M:%S"
INSERT_MESSAGE_SQL: str = """
INSERT INTO messaging_messages (
    instance_id, direction, chat_id, chat_type, sender_id, sender_name, is_self, text,
    message_id, reply_to, attachments_json, occurred_at, raw_json, raw_ref, dedup_key
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?)
ON CONFLICT (instance_id, dedup_key) WHERE dedup_key <> '' DO NOTHING
"""


@dataclass(frozen=True)
class StoreResult:
    """``stored`` is a new row, ``updated`` an edit applied to an existing row."""

    message_id: int
    stored: bool
    updated: bool = False


@contextmanager
def transaction(settings: Settings, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """One short write transaction on the shared ``database.connect`` (spec 10.4)."""
    connection: sqlite3.Connection = connect(settings)
    try:
        if immediate:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def data_dir_of(settings: Settings) -> Path:
    return settings.data_dir.resolve()


def find_by_dedup(connection: sqlite3.Connection, instance_id: int, dedup_key: str) -> int | None:
    row: sqlite3.Row | None = connection.execute(
        "SELECT id FROM messaging_messages WHERE instance_id = ? AND dedup_key = ?",
        (instance_id, dedup_key),
    ).fetchone()
    return None if row is None else int(row[0])


def message_params(message: InboundMessage, raw_json: str) -> tuple[object, ...]:
    attachments: str = json.dumps(
        [attachment_to_dict(item) for item in message.attachments],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        message.session.instance_id,
        message.direction,
        message.session.address,
        message.session.legacy_chat_type,
        message.sender.id,
        message.sender.name,
        1 if message.sender.is_self else 0,
        message.text,
        message.platform_message_id,
        message.reply_to,
        attachments,
        message.occurred_at,
        raw_json,
        message.dedup_key,
    )


def store_inbound(
    settings: Settings, message: InboundMessage, now: datetime | None = None
) -> StoreResult:
    """Insert once per ``(instance_id, dedup_key)``; an edit only rewrites ``text``."""
    stored_at: datetime = now or datetime.now(UTC)
    raw_text: str = encode_raw(message.raw)
    offload: bool = needs_offload(raw_text) if raw_text else False
    written: Path | None = None
    try:
        with transaction(settings, immediate=True) as connection:
            instance_id: int = message.session.instance_id
            existing: int | None = find_by_dedup(connection, instance_id, message.dedup_key)
            if existing is not None:
                if not message.edit:
                    return StoreResult(existing, stored=False)
                connection.execute(
                    "UPDATE messaging_messages SET text = ? WHERE id = ?",
                    (message.text, existing),
                )
                return StoreResult(existing, stored=False, updated=True)
            cursor: sqlite3.Cursor = connection.execute(
                INSERT_MESSAGE_SQL, message_params(message, "" if offload else raw_text)
            )
            if cursor.rowcount == 0 or cursor.lastrowid is None:
                raced: int | None = find_by_dedup(connection, instance_id, message.dedup_key)
                return StoreResult(raced or 0, stored=False)
            message_id: int = int(cursor.lastrowid)
            if offload:
                relative: str = raw_relative_path(message_id, stored_at)
                written = write_raw_file(data_dir_of(settings), relative, raw_text)
                connection.execute(
                    "UPDATE messaging_messages SET raw_ref = ? WHERE id = ?",
                    (relative, message_id),
                )
            return StoreResult(message_id, stored=True)
    except BaseException:
        if written is not None:
            written.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class OutboxEntry:
    id: int
    user_id: int
    kind: str
    instance_id: int | None
    route_id: int | None
    session: str
    payload: dict[str, object]
    idempotency_key: str
    status: str
    attempts: int
    next_attempt_at: str
    give_up_at: str
    platform_message_id: str
    last_error: str

    @property
    def delivery_id(self) -> str:
        return f"d_{self.id}"


def fmt(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(TIME_FORMAT)


def row_to_entry(row: sqlite3.Row) -> OutboxEntry:
    payload: object = json.loads(str(row["payload_json"]) or "{}")
    return OutboxEntry(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        kind=str(row["kind"]),
        instance_id=None if row["instance_id"] is None else int(row["instance_id"]),
        route_id=None if row["route_id"] is None else int(row["route_id"]),
        session=str(row["session"]),
        payload=payload if isinstance(payload, dict) else {},
        idempotency_key=str(row["idempotency_key"]),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        next_attempt_at=str(row["next_attempt_at"]),
        give_up_at=str(row["give_up_at"]),
        platform_message_id=str(row["platform_message_id"]),
        last_error=str(row["last_error"]),
    )


def fetch(connection: sqlite3.Connection, entry_id: int) -> OutboxEntry | None:
    row: sqlite3.Row | None = connection.execute(
        "SELECT * FROM router_outbox WHERE id = ?", (entry_id,)
    ).fetchone()
    return None if row is None else row_to_entry(row)


def read_raw(
    settings: Settings, instance_id: int, message_id: int, raw_json: str, raw_ref: str
) -> dict[str, object] | None:
    """Reconstruct ``raw`` from the inline column or from the offloaded file."""
    del instance_id, message_id
    if raw_json:
        try:
            parsed: object = json.loads(raw_json)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    if not raw_ref:
        return None
    path: Path = settings.database_path.parent / raw_ref
    if not path.is_file():
        return None
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None
