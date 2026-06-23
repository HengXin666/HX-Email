import sqlite3

from hx_email.config import Settings
from hx_email.database import migrate


def test_migrate_creates_sqlite_database_in_configured_data_dir(tmp_path):
    settings = Settings(data_dir=tmp_path / "hx-data")

    database_path = migrate(settings)

    assert database_path == tmp_path / "hx-data" / "hx_email.sqlite3"
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        registration_enabled = connection.execute(
            "SELECT value FROM system_settings WHERE key = 'registration_enabled'"
        ).fetchone()[0]
        admin = connection.execute(
            "SELECT username, is_admin FROM users WHERE username = 'admin'"
        ).fetchone()
        email_accounts_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(email_accounts)").fetchall()
        }
        usable_email_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(usable_emails)").fetchall()
        }
        temp_mailbox_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(temp_mailboxes)").fetchall()
        }
        platform_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(platforms)").fetchall()
        }
        platform_binding_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(platform_bindings)").fetchall()
        }

    assert version == 5
    assert registration_enabled == "false"
    assert admin == ("admin", 1)
    assert {"provider", "primary_address", "status"}.issubset(email_accounts_columns)
    assert {"email_account_id", "kind", "status", "group_id"}.issubset(usable_email_columns)
    assert {"user_id", "usable_email_id", "provider", "provider_mailbox_id"}.issubset(
        temp_mailbox_columns
    )
    assert {"user_id", "name"}.issubset(platform_columns)
    assert {"user_id", "usable_email_id", "platform_id", "status", "notes"}.issubset(
        platform_binding_columns
    )
