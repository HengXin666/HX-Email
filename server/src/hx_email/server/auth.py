import secrets
from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import hash_password, verify_password


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    username: str
    is_admin: bool


def require_inserted_id(value: int | None) -> int:
    if value is None:
        raise RuntimeError("SQLite did not return an inserted row id")
    return value


def login(settings: Settings, username: str, password: str) -> tuple[AuthenticatedUser, str] | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id, username, password_hash, is_admin
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    if row is None or not verify_password(password, row["password_hash"]):
        return None

    user = AuthenticatedUser(
        id=row["id"],
        username=row["username"],
        is_admin=bool(row["is_admin"]),
    )
    token = secrets.token_urlsafe(32)
    return user, create_session(settings, user, token)


def authenticate_token(settings: Settings, token: str) -> AuthenticatedUser | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT users.id, users.username, users.is_admin
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()

    if row is None:
        return None

    return AuthenticatedUser(
        id=row["id"],
        username=row["username"],
        is_admin=bool(row["is_admin"]),
    )


def registration_enabled(settings: Settings) -> bool:
    with connect(settings) as connection:
        value = connection.execute(
            "SELECT value FROM system_settings WHERE key = 'registration_enabled'"
        ).fetchone()["value"]

    setting_value: str = str(value)
    return setting_value == "true"


def set_registration_enabled(settings: Settings, enabled: bool) -> bool:
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE system_settings
            SET value = ?
            WHERE key = 'registration_enabled'
            """,
            ("true" if enabled else "false",),
        )

    return enabled


def register_user(settings: Settings, username: str, password: str) -> AuthenticatedUser:
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (username, password_hash, is_admin)
            VALUES (?, ?, 0)
            """,
            (username, hash_password(password)),
        )

    return AuthenticatedUser(
        id=require_inserted_id(cursor.lastrowid),
        username=username,
        is_admin=False,
    )


def create_session(settings: Settings, user: AuthenticatedUser, token: str | None = None) -> str:
    token = token or secrets.token_urlsafe(32)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO sessions (token, user_id) VALUES (?, ?)",
            (token, user.id),
        )
    return token


def revoke_session(settings: Settings, token: str) -> None:
    with connect(settings) as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))


def update_credentials(
    settings: Settings,
    user: AuthenticatedUser,
    username: str,
    password: str,
) -> AuthenticatedUser:
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE users
            SET username = ?, password_hash = ?
            WHERE id = ?
            """,
            (username, hash_password(password), user.id),
        )

    return AuthenticatedUser(id=user.id, username=username, is_admin=user.is_admin)
