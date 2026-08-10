"""Merge mailbox data tables (temp mailboxes, pool, readings, messages)."""

from __future__ import annotations

import sqlite3
from typing import Any

from hx_email.server.sync.impl.merge import optional_remap, strict_remap


def merge_temp_mailboxes(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    email_ids: dict[int, int],
    rows: list[dict[str, Any]],
    overwrite: bool = True,
) -> None:
    for row in rows:
        user_id: int = strict_remap(user_ids, row["user_id"])
        email_id: int = strict_remap(email_ids, row["usable_email_id"])
        existing = connection.execute(
            "SELECT id FROM temp_mailboxes WHERE user_id = ? AND usable_email_id = ?",
            (user_id, email_id),
        ).fetchone()
        if existing is not None:
            if overwrite:
                connection.execute(
                    "UPDATE temp_mailboxes SET provider = ?, provider_mailbox_id = ? WHERE id = ?",
                    (row["provider"], row["provider_mailbox_id"], existing[0]),
                )
        else:
            connection.execute(
                "INSERT INTO temp_mailboxes (user_id, usable_email_id, provider,"
                " provider_mailbox_id) VALUES (?, ?, ?, ?)",
                (user_id, email_id, row["provider"], row["provider_mailbox_id"]),
            )


def merge_mail_pool_entries(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    email_ids: dict[int, int],
    rows: list[dict[str, Any]],
    overwrite: bool = True,
) -> None:
    for row in rows:
        user_id: int = strict_remap(user_ids, row["user_id"])
        email_id: int = strict_remap(email_ids, row["usable_email_id"])
        existing = connection.execute(
            "SELECT id FROM mail_pool_entries WHERE user_id = ? AND usable_email_id = ?",
            (user_id, email_id),
        ).fetchone()
        if existing is not None:
            if overwrite:
                connection.execute(
                    "UPDATE mail_pool_entries SET status = ?, claim_key = ?,"
                    " claimed_project_key = ?, completed_project_key = ? WHERE id = ?",
                    (
                        row["status"],
                        row["claim_key"],
                        row["claimed_project_key"],
                        row["completed_project_key"],
                        existing[0],
                    ),
                )
        else:
            connection.execute(
                "INSERT INTO mail_pool_entries (user_id, usable_email_id, status, claim_key,"
                " claimed_project_key, completed_project_key) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    email_id,
                    row["status"],
                    row["claim_key"],
                    row["claimed_project_key"],
                    row["completed_project_key"],
                ),
            )


def merge_verification_readings(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    email_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        connection.execute(
            "INSERT OR IGNORE INTO verification_readings (user_id, usable_email_id, code, link,"
            " recipient_address, certainty, subject, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                strict_remap(user_ids, row["user_id"]),
                strict_remap(email_ids, row["usable_email_id"]),
                row["code"],
                row["link"],
                row["recipient_address"],
                row["certainty"],
                row["subject"],
                row["created_at"],
            ),
        )


def merge_fetched_messages(
    connection: sqlite3.Connection,
    user_ids: dict[int, int],
    email_ids: dict[int, int],
    account_ids: dict[int, int],
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        connection.execute(
            "INSERT OR IGNORE INTO fetched_messages (user_id, usable_email_id, email_account_id,"
            " from_address, recipient_address, subject, body, message_id, body_hash,"
            " received_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                strict_remap(user_ids, row["user_id"]),
                strict_remap(email_ids, row["usable_email_id"]),
                optional_remap(account_ids, row["email_account_id"]),
                row["from_address"],
                row["recipient_address"],
                row["subject"],
                row["body"],
                row["message_id"],
                row["body_hash"],
                row["received_at"],
                row["created_at"],
            ),
        )
