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

    assert version == 2
    assert registration_enabled == "false"
    assert admin == ("admin", 1)
