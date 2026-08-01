"""Schema migration for durable new-mail delivery jobs."""

import sqlite3


def migrate_message_delivery_schema(connection: sqlite3.Connection) -> None:
    """Create the outbox used by email forwarding and notification pipelines."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS message_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_message_id INTEGER NOT NULL REFERENCES fetched_messages(id),
            channel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            delivered_at TEXT,
            UNIQUE(fetched_message_id, channel)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_message_deliveries_pending
        ON message_deliveries(status, attempts, id)
        """
    )
