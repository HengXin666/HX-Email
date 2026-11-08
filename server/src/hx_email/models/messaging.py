"""Schema migration for messaging plugin instances, messages and the router layer.

Router tables follow docs/messaging-router.md section 4. Every statement is idempotent,
so running the migration repeatedly on an existing database is safe.
"""

import sqlite3
from typing import Final

MESSAGE_ROUTER_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("is_self", "INTEGER NOT NULL DEFAULT 0"),
    ("reply_to", "TEXT NOT NULL DEFAULT ''"),
    ("attachments_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("occurred_at", "TEXT NOT NULL DEFAULT ''"),
    ("raw_ref", "TEXT NOT NULL DEFAULT ''"),
    ("dedup_key", "TEXT NOT NULL DEFAULT ''"),
)
ROUTE_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("name", "TEXT NOT NULL DEFAULT ''"),
    ("updated_at", "TEXT NOT NULL DEFAULT ''"),
    ("push_cursor", "INTEGER NOT NULL DEFAULT 0"),
)


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
    migrate_router_schema(connection)


def add_missing_message_columns(connection: sqlite3.Connection) -> None:
    """SQLite has no ADD COLUMN IF NOT EXISTS, so read table_info and add only gaps."""
    rows: list[sqlite3.Row] = connection.execute("PRAGMA table_info(messaging_messages)").fetchall()
    existing: set[str] = {str(row[1]) for row in rows}
    for name, definition in MESSAGE_ROUTER_COLUMNS:
        if name not in existing:
            connection.execute(f"ALTER TABLE messaging_messages ADD COLUMN {name} {definition}")


def add_missing_route_columns(connection: sqlite3.Connection) -> None:
    """Subscriptions need a display name, an update stamp and a per-user index."""
    rows: list[sqlite3.Row] = connection.execute("PRAGMA table_info(router_routes)").fetchall()
    existing: set[str] = {str(row[1]) for row in rows}
    for name, definition in ROUTE_COLUMNS:
        if name not in existing:
            connection.execute(f"ALTER TABLE router_routes ADD COLUMN {name} {definition}")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_router_routes_user ON router_routes(user_id, id)"
    )


# 路由层订阅与分发的决策记录, 实现规格见 docs/messaging-router.md
# .agents/notes/implemented/feature/2026-11-02-messaging-router-gateway.md
# GitHub App 一键创建与秘密字段只写不读的决策
# 决策记录: .agents/notes/implemented/feature/2026-11-03-github-app-manifest-flow.md
def migrate_router_schema(connection: sqlite3.Connection) -> None:
    """Router layer: dedup index, routes, outbox, ingress deliveries, API keys."""
    add_missing_message_columns(connection)
    # Permanent unique index; legacy rows keep dedup_key = '' and stay outside it.
    # Old rows age out through the retention housekeeping, not through a time window.
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_messaging_messages_dedup
        ON messaging_messages(instance_id, dedup_key) WHERE dedup_key <> ''
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messaging_messages_created
        ON messaging_messages(created_at)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS router_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            source_prefix TEXT NOT NULL,
            filter_json TEXT NOT NULL DEFAULT '{}',
            delivery TEXT NOT NULL,
            target_encrypted TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            ack_cursor INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT
        )
        """
    )
    add_missing_route_columns(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS router_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            kind TEXT NOT NULL,
            instance_id INTEGER REFERENCES messaging_instances(id),
            route_id INTEGER REFERENCES router_routes(id),
            session TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
            give_up_at TEXT NOT NULL,
            platform_message_id TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            CHECK (
                (kind = 'send' AND instance_id IS NOT NULL AND route_id IS NULL AND session <> '')
                OR (kind = 'webhook' AND route_id IS NOT NULL AND instance_id IS NULL)
            )
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_router_outbox_send
        ON router_outbox(instance_id, idempotency_key) WHERE kind = 'send'
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_router_outbox_webhook
        ON router_outbox(route_id, idempotency_key) WHERE kind = 'webhook'
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_router_outbox_due
        ON router_outbox(status, next_attempt_at)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS router_ingress_deliveries (
            instance_id INTEGER NOT NULL REFERENCES messaging_instances(id),
            delivery_id TEXT NOT NULL,
            event TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            payload_encrypted TEXT NOT NULL DEFAULT '',
            received_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (instance_id, delivery_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS router_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_used_at TEXT,
            revoked_at TEXT
        )
        """
    )
    # GitHub App Manifest 一键创建的一次性 state, 10 分钟有效, 回调用 UPDATE ... WHERE used = 0 消费
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS router_github_app_states (
            state TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            instance_id INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_router_github_app_states_created
        ON router_github_app_states(created_at)
        """
    )
