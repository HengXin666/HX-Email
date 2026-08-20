"""Schema migrations for feature-added columns and the platform-rules table.

fetched_messages 的 HTML 正文 / 发件人邮箱列是收信 HTML 渲染与别名识别的
数据基础; platform_rules 承载用户自定义的平台识别规则(见 workspace 平台识别)。
"""

from __future__ import annotations

import sqlite3


def column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in connection.execute(f"PRAGMA table_info({table})"))


COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("usable_emails", "email_account_id", "INTEGER REFERENCES email_accounts(id)"),
    ("usable_emails", "kind", "TEXT NOT NULL DEFAULT 'custom'"),
    ("usable_emails", "status", "TEXT NOT NULL DEFAULT 'active'"),
    ("usable_emails", "created_at", "TEXT NOT NULL DEFAULT ''"),
    ("usable_emails", "group_id", "INTEGER REFERENCES groups(id)"),
    ("usable_emails", "notify_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("email_accounts", "imap_password", "TEXT NOT NULL DEFAULT ''"),
    ("email_accounts", "client_id", "TEXT NOT NULL DEFAULT ''"),
    ("email_accounts", "refresh_token", "TEXT NOT NULL DEFAULT ''"),
    ("email_accounts", "last_refresh_at", "TEXT"),
    ("email_accounts", "group_id", "INTEGER REFERENCES groups(id)"),
    ("email_accounts", "remark", "TEXT NOT NULL DEFAULT ''"),
    ("email_accounts", "telegram_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("groups", "proxy_url", "TEXT NOT NULL DEFAULT ''"),
    ("groups", "notify_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("groups", "sort_order", "INTEGER NOT NULL DEFAULT 0"),
    ("fetched_messages", "message_id", "TEXT NOT NULL DEFAULT ''"),
    ("fetched_messages", "body_html", "TEXT NOT NULL DEFAULT ''"),
    ("fetched_messages", "from_email", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "expires_at", "TEXT NOT NULL DEFAULT ''"),
)


def apply_column_migrations(connection: sqlite3.Connection) -> None:
    for table, column, definition in COLUMN_MIGRATIONS:
        if not column_exists(connection, table, column):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate_platform_rules_schema(connection: sqlite3.Connection) -> None:
    """Create the per-user platform recognition rules table."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL DEFAULT '',
            match_field TEXT NOT NULL DEFAULT 'domain',
            match_type TEXT NOT NULL DEFAULT 'contains',
            pattern TEXT NOT NULL DEFAULT '',
            platform_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_platform_rules_user
        ON platform_rules(user_id, enabled)
        """
    )
