"""Schema migration for per-group automatic mail polling."""

import sqlite3


def migrate_polling_schema(connection: sqlite3.Connection) -> None:
    """Add the polling flag without changing existing group behavior."""
    columns: set[str] = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(groups)").fetchall()
    }
    if "polling_enabled" not in columns:
        connection.execute(
            "ALTER TABLE groups ADD COLUMN polling_enabled INTEGER NOT NULL DEFAULT 1"
        )
