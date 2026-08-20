import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from hx_email.config import Settings
from hx_email.models import (
    migrate_account_timestamps_schema,
    migrate_message_delivery_schema,
    migrate_messaging_schema,
    migrate_polling_schema,
)
from hx_email.models.schema_migrations import (
    apply_column_migrations,
    migrate_platform_rules_schema,
)
from hx_email.security import hash_password, migrate_stored_secrets


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def connect(settings: Settings) -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def migrate(settings: Settings) -> Path:
    database_path = settings.database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                expires_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS usable_emails (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                email_account_id INTEGER REFERENCES email_accounts(id),
                address TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'primary',
                status TEXT NOT NULL DEFAULT 'active',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(user_id, address)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS email_accounts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                provider TEXT NOT NULL,
                primary_address TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                imap_host TEXT NOT NULL DEFAULT '',
                imap_port INTEGER,
                username TEXT NOT NULL DEFAULT '',
                imap_password TEXT NOT NULL DEFAULT '',
                client_id TEXT NOT NULL DEFAULT '',
                refresh_token TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                last_refresh_at TEXT,
                created_at TEXT NOT NULL DEFAULT '',
                last_fetch_at TEXT,
                refresh_failed_at TEXT,
                UNIQUE(user_id, primary_address)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#58a6ff',
                UNIQUE(user_id, name)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#238636',
                UNIQUE(user_id, name)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS usable_email_tags (
                usable_email_id INTEGER NOT NULL REFERENCES usable_emails(id),
                tag_id INTEGER NOT NULL REFERENCES tags(id),
                PRIMARY KEY (usable_email_id, tag_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS temp_mailboxes (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                usable_email_id INTEGER NOT NULL REFERENCES usable_emails(id),
                provider TEXT NOT NULL,
                provider_mailbox_id TEXT NOT NULL,
                UNIQUE(user_id, usable_email_id),
                UNIQUE(user_id, provider, provider_mailbox_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS platforms (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                UNIQUE(user_id, name)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_bindings (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                usable_email_id INTEGER NOT NULL REFERENCES usable_emails(id),
                platform_id INTEGER NOT NULL REFERENCES platforms(id),
                status TEXT NOT NULL DEFAULT 'active',
                notes TEXT NOT NULL DEFAULT '',
                UNIQUE(user_id, usable_email_id, platform_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_readings (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                usable_email_id INTEGER NOT NULL REFERENCES usable_emails(id),
                code TEXT,
                link TEXT,
                recipient_address TEXT,
                certainty TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_vrf_dedup"
            " ON verification_readings(usable_email_id, code)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mail_pool_entries (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                usable_email_id INTEGER NOT NULL REFERENCES usable_emails(id),
                status TEXT NOT NULL DEFAULT 'available',
                claim_key TEXT NOT NULL DEFAULT '',
                claimed_project_key TEXT NOT NULL DEFAULT '',
                completed_project_key TEXT NOT NULL DEFAULT '',
                UNIQUE(user_id, usable_email_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                message TEXT DEFAULT '',
                error_detail TEXT DEFAULT '',
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (account_id) REFERENCES email_accounts(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id INTEGER,
                detail TEXT DEFAULT '',
                ip_address TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fetched_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
                usable_email_id INTEGER NOT NULL REFERENCES usable_emails(id),
                email_account_id INTEGER REFERENCES email_accounts(id),
                from_address TEXT NOT NULL DEFAULT '', recipient_address TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
                message_id TEXT NOT NULL DEFAULT '', body_hash TEXT NOT NULL DEFAULT '',
                received_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        apply_column_migrations(connection)
        connection.execute(
            "UPDATE usable_emails SET created_at = ? WHERE created_at = ''",
            (utc_now_iso(),),
        )
        migrate_polling_schema(connection)
        migrate_message_delivery_schema(connection)
        migrate_account_timestamps_schema(connection)
        migrate_messaging_schema(connection)
        migrate_platform_rules_schema(connection)
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fetched_msg_dedup
            ON fetched_messages(usable_email_id, from_address, subject, body_hash)
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO system_settings (key, value)
            VALUES ('registration_enabled', 'false')
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO users (username, password_hash, is_admin)
            VALUES (?, ?, 1)
            """,
            (settings.admin_username, hash_password(settings.admin_password)),
        )
        connection.execute("PRAGMA user_version = 11")
        migrate_stored_secrets(settings, connection)
    return database_path
