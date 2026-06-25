"""Message persistence - store and query fetched emails for incremental sync."""

from __future__ import annotations

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
    import hashlib

    with connect(settings) as conn:
        for msg in messages:
            body_hash = hashlib.sha256(
                (msg.body or "").encode("utf-8", errors="replace")
            ).hexdigest()[:32]
            from_addr = msg.from_address or ""

            # Check duplicate
            exists = conn.execute(
                """
                SELECT 1 FROM fetched_messages
                WHERE usable_email_id = ?
                  AND from_address = ?
                  AND subject = ?
                  AND body_hash = ?
                """,
                (usable_email_id, from_addr, msg.subject, body_hash),
            ).fetchone()
            if exists:
                continue

            conn.execute(
                """
                INSERT INTO fetched_messages (
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
                    msg.subject or "",
                    msg.body or "",
                    msg.received_at or now_iso(),
                    body_hash,
                ),
            )
            inserted += 1

    return inserted


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
            ORDER BY id DESC
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


def delete_messages_for_email(settings: Settings, usable_email_id: int) -> int:
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
