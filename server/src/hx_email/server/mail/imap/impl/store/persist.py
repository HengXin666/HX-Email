"""Persisting fetched messages: dedup, bodies, and the IMAP UID."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import UTC
from typing import TYPE_CHECKING

from hx_email.config import Settings
from hx_email.database import connect

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from hx_email.server.mail import MailboxMessage

# Bodies above this are not stored: readers only need tokens and headers, and the row
# keeps the message's UID so the incremental window still advances.
MAX_STORED_BODY_BYTES: int = 256 * 1024


def save_messages(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    email_account_id: int,
    messages: list[MailboxMessage],
) -> int:
    """Persist fetched messages, skipping duplicates by body hash."""
    if not messages:
        return 0

    inserted_ids: list[int] = []
    with connect(settings) as conn:
        for msg in messages:
            from_addr = msg.from_address or ""
            subject = msg.subject or ""
            received_at = msg.received_at or ""
            message_id = msg.message_id or ""
            body_hash = message_dedup_hash(msg, received_at)
            legacy_hash = legacy_body_hash(msg.body or "")
            if message_already_saved(
                conn, usable_email_id, from_addr, subject, received_at, body_hash, legacy_hash
            ):
                backfill_message_uid(
                    conn,
                    usable_email_id,
                    from_addr,
                    subject,
                    received_at,
                    body_hash,
                    legacy_hash,
                    message_id,
                )
                continue

            body_text, body_html = storable_bodies(msg)
            # INSERT OR IGNORE: atomic dedup via the UNIQUE index, no TOCTOU race
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO fetched_messages (
                    user_id, usable_email_id, email_account_id,
                    from_address, from_email, recipient_address, subject, body,
                    body_html, message_id, received_at, body_hash, folder
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    usable_email_id,
                    email_account_id,
                    from_addr,
                    msg.from_email or "",
                    msg.recipient_address or "",
                    subject,
                    body_text,
                    body_html,
                    message_id,
                    received_at or now_iso(),
                    body_hash,
                    msg.folder or "inbox",
                ),
            )
            if cursor.rowcount > 0 and cursor.lastrowid is not None:
                inserted_ids.append(int(cursor.lastrowid))

    if inserted_ids:
        try:
            from hx_email.server.notifications import dispatch_new_messages

            dispatch_new_messages(settings, inserted_ids)
        except Exception:
            logger.exception("Failed to enqueue new-mail deliveries")
    return len(inserted_ids)


def storable_bodies(message: MailboxMessage) -> tuple[str, str]:
    """Return the (text, html) bodies to persist, blanking oversized ones."""
    body_text: str = message.body or ""
    body_html: str = message.body_html or ""
    if len(body_text.encode("utf-8", errors="replace")) > MAX_STORED_BODY_BYTES:
        return "", ""
    return body_text, body_html


def message_dedup_hash(message: MailboxMessage, received_at: str) -> str:
    key = (message.message_id or "").strip() or received_at.strip()
    if not key:
        return legacy_body_hash(message.body or "")
    return legacy_body_hash(key + chr(10) + (message.body or ""))


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


def backfill_message_uid(
    conn: sqlite3.Connection,
    usable_email_id: int,
    from_address: str,
    subject: str,
    received_at: str,
    body_hash: str,
    legacy_hash: str,
    message_id: str,
) -> None:
    """Stamp the provider UID onto a row stored before UIDs were kept.

    ``message_id`` drives the incremental UID window, so a legacy row without it
    would keep an account re-reading its whole folder.
    """
    if not message_id:
        return
    match = (
        "usable_email_id = ? AND from_address = ? AND subject = ? "
        "AND received_at = ? AND body_hash IN (?, ?)"
    )
    conn.execute(
        f"UPDATE fetched_messages SET message_id = ? WHERE {match} AND message_id = ''",
        (message_id, usable_email_id, from_address, subject, received_at, body_hash, legacy_hash),
    )


def now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
