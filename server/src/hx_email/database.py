import sqlite3
from pathlib import Path

from hx_email.config import Settings


def migrate(settings: Settings) -> Path:
    database_path = settings.database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA user_version = 1")

    return database_path
