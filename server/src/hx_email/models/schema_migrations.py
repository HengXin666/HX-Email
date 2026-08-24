"""Schema migrations for feature-added columns, platform rules and sync WAL.

fetched_messages 的 HTML 正文 / 发件人邮箱列是收信 HTML 渲染与别名识别的
数据基础; platform_rules 承载用户自定义的平台识别规则(见 workspace 平台识别)。
sync_changelog/sync_suppress 是主从同步的增量 WAL: 业务写自动触发记录,
merge 应用期间通过 suppress 表抑制, 实现「常规增量 + 周期全量」的 PG 风格同步。
"""

from __future__ import annotations

import sqlite3

# 参与增量同步的表: 有整数主键 id 的表 (触发器以 NEW.id 定位变更行)。
# system_settings / usable_email_tags 无 id 主键, 由周期全量路径同步;
# merge_snapshot 仍会合并它们, 增量包不含这两张表也不会丢数据。
SYNC_TABLES: tuple[str, ...] = (
    "users",
    "groups",
    "tags",
    "email_accounts",
    "usable_emails",
    "platforms",
    "platform_bindings",
    "temp_mailboxes",
    "mail_pool_entries",
    "verification_readings",
    "fetched_messages",
)


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
    ("groups", "allowed_provider", "TEXT NOT NULL DEFAULT ''"),
    ("fetched_messages", "message_id", "TEXT NOT NULL DEFAULT ''"),
    ("fetched_messages", "body_html", "TEXT NOT NULL DEFAULT ''"),
    ("fetched_messages", "from_email", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "expires_at", "TEXT NOT NULL DEFAULT ''"),
    ("refresh_logs", "round_id", "INTEGER"),
)


def apply_column_migrations(connection: sqlite3.Connection) -> None:
    for table, column, definition in COLUMN_MIGRATIONS:
        if not column_exists(connection, table, column):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate_refresh_rounds_schema(connection: sqlite3.Connection) -> None:
    """刷新轮次表: 一次批量/单账号刷新 = 一轮, refresh_logs.round_id 关联日志."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            scope TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            total INTEGER NOT NULL DEFAULT 0,
            success INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            finished_at TEXT NOT NULL DEFAULT ''
        )
        """
    )


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
    if not column_exists(connection, "platform_rules", "patterns"):
        connection.execute(
            "ALTER TABLE platform_rules ADD COLUMN patterns TEXT NOT NULL DEFAULT '[]'"
        )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_platform_rules_user
        ON platform_rules(user_id, enabled)
        """
    )


def migrate_sync_wal_schema(connection: sqlite3.Connection) -> None:
    """Create the incremental-sync WAL tables and per-table capture triggers.

    sync_changelog records every business INSERT/UPDATE on SYNC_TABLES (the
    "WAL" of the PG-style replication design); sync_suppress lets a merge or
    delta-apply transaction mute capture so applied rows are not re-broadcast.
    Triggers read the suppress flag, so capture is fully automatic.
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            row_id INTEGER NOT NULL,
            op TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_changelog_created
        ON sync_changelog(created_at)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_suppress (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            active INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute("INSERT OR IGNORE INTO sync_suppress (id, active) VALUES (1, 0)")
    for table in SYNC_TABLES:
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_sync_{table}_insert
            AFTER INSERT ON {table}
            WHEN (SELECT active FROM sync_suppress WHERE id = 1) = 0
            BEGIN
                INSERT INTO sync_changelog (table_name, row_id, op, created_at)
                VALUES ('{table}', NEW.id, 'insert',
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            END
            """
        )
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS trg_sync_{table}_update
            AFTER UPDATE ON {table}
            WHEN (SELECT active FROM sync_suppress WHERE id = 1) = 0
            BEGIN
                INSERT INTO sync_changelog (table_name, row_id, op, created_at)
                VALUES ('{table}', NEW.id, 'update',
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            END
            """
        )
