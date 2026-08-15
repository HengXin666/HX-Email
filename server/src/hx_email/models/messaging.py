"""Schema migration for messaging plugin instances and messages."""

import sqlite3


def migrate_messaging_schema(connection: sqlite3.Connection) -> None:
    """Create tables backing pluggable IM adapters (QQ/WeChat/TG/Discord)."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS messaging_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'stopped',
            config_encrypted TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messaging_instances_user
        ON messaging_instances(user_id, id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS messaging_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id INTEGER NOT NULL REFERENCES messaging_instances(id),
            direction TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            chat_type TEXT NOT NULL,
            sender_id TEXT NOT NULL DEFAULT '',
            sender_name TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            message_id TEXT NOT NULL DEFAULT '',
            raw_json TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messaging_messages_instance_chat
        ON messaging_messages(instance_id, chat_id, id)
        """
    )
