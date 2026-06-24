import sqlite3
from pathlib import Path

from hx_email.config import Settings
from hx_email.security import hash_password


def column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def connect(settings: Settings) -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
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
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id)
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
                UNIQUE(user_id, address)
            )
            """
        )
        if not column_exists(connection, "usable_emails", "email_account_id"):
            connection.execute(
                """
                ALTER TABLE usable_emails
                ADD COLUMN email_account_id INTEGER REFERENCES email_accounts(id)
                """
            )
        if not column_exists(connection, "usable_emails", "kind"):
            connection.execute(
                "ALTER TABLE usable_emails ADD COLUMN kind TEXT NOT NULL DEFAULT 'custom'"
            )
        if not column_exists(connection, "usable_emails", "status"):
            connection.execute(
                "ALTER TABLE usable_emails ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
        if not column_exists(connection, "usable_emails", "group_id"):
            connection.execute(
                "ALTER TABLE usable_emails ADD COLUMN group_id INTEGER REFERENCES groups(id)"
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
                UNIQUE(user_id, primary_address)
            )
            """
        )
        if not column_exists(connection, "email_accounts", "imap_password"):
            connection.execute(
                "ALTER TABLE email_accounts ADD COLUMN imap_password TEXT NOT NULL DEFAULT ''"
            )
        if not column_exists(connection, "email_accounts", "client_id"):
            connection.execute(
                "ALTER TABLE email_accounts ADD COLUMN client_id TEXT NOT NULL DEFAULT ''"
            )
        if not column_exists(connection, "email_accounts", "refresh_token"):
            connection.execute(
                "ALTER TABLE email_accounts ADD COLUMN refresh_token TEXT NOT NULL DEFAULT ''"
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
        connection.execute("PRAGMA user_version = 6")

    return database_path
