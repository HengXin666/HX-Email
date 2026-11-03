"""Reading and dropping persisted messages (newest first)."""

from __future__ import annotations

import sqlite3
from sqlite3 import Row

from hx_email.config import Settings
from hx_email.database import connect


def get_messages(
    settings: Settings,
    usable_email_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, object]]:
    """List persisted messages for a usable_email, newest first (按收信时间倒序)."""
    with connect(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, from_address, from_email, recipient_address, subject,
                   body, body_html, message_id, received_at, created_at, folder
            FROM fetched_messages
            WHERE usable_email_id = ?
            ORDER BY received_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (usable_email_id, limit, offset),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_message_count(settings: Settings, usable_email_id: int) -> int:
    with connect(settings) as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM fetched_messages WHERE usable_email_id = ?",
            (usable_email_id,),
        ).fetchone()
    return row["cnt"] if row else 0


def get_latest_message_uid(
    settings: Settings,
    email_account_id: int,
    folder: str = "inbox",
) -> str:
    """Highest numeric UID seen in one folder; drives incremental fetch.

    Every IMAP mailbox has its own UID space, so the watermark has to be scoped
    to the folder it will filter. QQ/163/126 hand out UID numbers per mailbox and
    the junk folder can sit far above the whole inbox range (measured: inbox
    8306-8312 vs junk 47309-47317 on one QQ account); taking the account-wide
    maximum as the inbox watermark filtered every new inbox message away and the
    account stopped receiving mail with no error reported.
    """
    with connect(settings) as conn:
        row = conn.execute(
            """
            SELECT message_id FROM fetched_messages
            WHERE email_account_id = ?
              AND folder = ?
              AND message_id != ''
              AND message_id NOT GLOB '*[^0-9]*'
            ORDER BY CAST(message_id AS INTEGER) DESC LIMIT 1
            """,
            (email_account_id, folder),
        ).fetchone()
    return str(row["message_id"]) if row is not None else ""


def delete_messages_for_email(
    settings: Settings,
    usable_email_id: int,
    *,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Delete every stored message (and its deliveries) for a usable_email.

    An optional connection reuses the caller transaction, which avoids SQLite
    "database is locked" errors from concurrent writers.
    """
    if connection is not None:
        connection.execute(
            "DELETE FROM message_deliveries WHERE fetched_message_id IN"
            " (SELECT id FROM fetched_messages WHERE usable_email_id = ?)",
            (usable_email_id,),
        )
        return connection.execute(
            "DELETE FROM fetched_messages WHERE usable_email_id = ?",
            (usable_email_id,),
        ).rowcount
    with connect(settings) as conn:
        conn.execute(
            "DELETE FROM message_deliveries WHERE fetched_message_id IN ("
            "SELECT id FROM fetched_messages WHERE usable_email_id = ?)",
            (usable_email_id,),
        )
        cursor = conn.execute(
            "DELETE FROM fetched_messages WHERE usable_email_id = ?",
            (usable_email_id,),
        )
        return cursor.rowcount


def row_to_dict(row: Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "from_address": row["from_address"],
        "from_email": row["from_email"],
        "recipient_address": row["recipient_address"],
        "subject": row["subject"],
        "body": row["body"],
        "body_html": row["body_html"],
        "message_id": row["message_id"],
        "received_at": row["received_at"],
        "created_at": row["created_at"],
        "folder": row["folder"] or "inbox",
    }
