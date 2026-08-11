"""Schema migration for per-account timeline timestamps."""

import sqlite3


def migrate_account_timestamps_schema(connection: sqlite3.Connection) -> None:
    """Add account timeline columns and backfill created_at from primary emails."""
    from hx_email.database import utc_now_iso

    columns: set[str] = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(email_accounts)").fetchall()
    }
    if "created_at" not in columns:
        connection.execute(
            "ALTER TABLE email_accounts ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
        )
    if "last_fetch_at" not in columns:
        connection.execute("ALTER TABLE email_accounts ADD COLUMN last_fetch_at TEXT")
    if "refresh_failed_at" not in columns:
        connection.execute("ALTER TABLE email_accounts ADD COLUMN refresh_failed_at TEXT")
    connection.execute(
        """
        UPDATE email_accounts
        SET created_at = COALESCE((
            SELECT MIN(ue.created_at) FROM usable_emails ue
            WHERE ue.email_account_id = email_accounts.id AND ue.created_at != ''
        ), '')
        WHERE created_at = ''
        """
    )
    connection.execute(
        "UPDATE email_accounts SET created_at = ? WHERE created_at = ''",
        (utc_now_iso(),),
    )
