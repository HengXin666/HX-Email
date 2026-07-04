"""Message persistence - store and query fetched emails for incremental sync."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC
from sqlite3 import Row
from typing import TYPE_CHECKING

from hx_email.config import Settings
from hx_email.database import connect

if TYPE_CHECKING:
    from hx_email.server.mail import MailboxMessage

# ── public API ───────────────────────────────────────────────────────────


def save_messages(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    email_account_id: int,
    messages: list[MailboxMessage],
) -> int:
    """Persist fetched messages, skipping duplicates by body hash.

    Returns count of newly inserted messages.
    """
    if not messages:
        return 0

    inserted = 0
    with connect(settings) as conn:
        for msg in messages:
            from_addr = msg.from_address or ""
            subject = msg.subject or ""
            received_at = msg.received_at or ""
            body_hash = message_dedup_hash(msg, received_at)
            legacy_hash = legacy_body_hash(msg.body or "")
            if message_already_saved(
                conn, usable_email_id, from_addr, subject, received_at, body_hash, legacy_hash
            ):
                continue

            # INSERT OR IGNORE: atomic dedup via UNIQUE index — no TOCTOU race
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO fetched_messages (
                    user_id, usable_email_id, email_account_id,
                    from_address, recipient_address, subject, body,
                    received_at, body_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    usable_email_id,
                    email_account_id,
                    from_addr,
                    msg.recipient_address or "",
                    subject,
                    msg.body or "",
                    received_at or now_iso(),
                    body_hash,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1

    return inserted


def message_dedup_hash(message: MailboxMessage, received_at: str) -> str:
    key = (message.message_id or "").strip() or received_at.strip()
    if not key:
        return legacy_body_hash(message.body or "")
    return legacy_body_hash(f"{key}\n{message.body or ''}")


def legacy_body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:32]


def message_already_saved(
    conn: sqlite3.Connection,
    usable_email_id: int,
    from_address: str,
    subject: str,
    received_at: str,
    body_hash: str,
    legacy_hash: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM fetched_messages
        WHERE usable_email_id = ?
          AND from_address = ?
          AND subject = ?
          AND received_at = ?
          AND body_hash IN (?, ?)
        LIMIT 1
        """,
        (usable_email_id, from_address, subject, received_at, body_hash, legacy_hash),
    ).fetchone()
    return row is not None


def get_messages(
    settings: Settings,
    usable_email_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, object]]:
    """List persisted messages for a usable_email, newest first."""
    with connect(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, from_address, recipient_address, subject,
                   body, received_at, created_at
            FROM fetched_messages
            WHERE usable_email_id = ?
            ORDER BY received_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (usable_email_id, limit, offset),
        ).fetchall()

    return [row_to_dict(r) for r in rows]


def get_message_count(settings: Settings, usable_email_id: int) -> int:
    with connect(settings) as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM fetched_messages WHERE usable_email_id = ?",
            (usable_email_id,),
        ).fetchone()
    return row["cnt"] if row else 0


def delete_messages_for_email(
    settings: Settings,
    usable_email_id: int,
    *,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Delete all fetched messages for a usable_email.

    Accepts an optional connection to reuse within a caller's transaction,
    avoiding SQLite "database is locked" errors from concurrent write connections.
    """
    if connection is not None:
        cursor = connection.execute(
            "DELETE FROM fetched_messages WHERE usable_email_id = ?",
            (usable_email_id,),
        )
        return cursor.rowcount
    with connect(settings) as conn:
        cursor = conn.execute(
            "DELETE FROM fetched_messages WHERE usable_email_id = ?",
            (usable_email_id,),
        )
        return cursor.rowcount


# ── helpers ──────────────────────────────────────────────────────────────


def now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def row_to_dict(row: Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "from_address": row["from_address"],
        "recipient_address": row["recipient_address"],
        "subject": row["subject"],
        "body": row["body"],
        "received_at": row["received_at"],
        "created_at": row["created_at"],
    }
