import secrets
import threading
import time
from dataclasses import dataclass, field

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import hash_password, verify_password


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    username: str
    is_admin: bool


LOGIN_MAX_FAILURES: int = 5
LOGIN_BASE_BACKOFF_SECONDS: float = 30.0
LOGIN_MAX_BACKOFF_SECONDS: float = 900.0
LOGIN_IDLE_CLEANUP_SECONDS: float = 3600.0
LOGIN_MAX_TRACKED_KEYS: int = 10_000


@dataclass
class _LoginAttemptState:
    failures: int = 0
    strikes: int = 0
    locked_until: float = 0.0
    last_activity: float = field(default_factory=time.monotonic)


class LoginRateLimiter:
    """Throttle login attempts per username and per source IP.

    Consecutive failures accumulate; once LOGIN_MAX_FAILURES is reached the
    key is locked with an exponentially growing window (base * 2 ** strikes,
    capped at LOGIN_MAX_BACKOFF_SECONDS).  A successful login resets the
    tracked state for both the username and the IP.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._states: dict[str, _LoginAttemptState] = {}

    @staticmethod
    def _keys(username: str, ip: str) -> tuple[str, str]:
        return f"user:{username}", f"ip:{ip}"

    def acquire(self, username: str, ip: str) -> float | None:
        """Return Retry-After seconds when locked for username or IP, else None."""
        now: float = time.monotonic()
        with self._lock:
            self._cleanup(now)
            for key in self._keys(username, ip):
                state: _LoginAttemptState | None = self._states.get(key)
                if state is not None and now < state.locked_until:
                    return max(1.0, state.locked_until - now)
        return None

    def record_failure(self, username: str, ip: str) -> None:
        now: float = time.monotonic()
        with self._lock:
            self._cleanup(now)
            for key in self._keys(username, ip):
                state: _LoginAttemptState = self._states.setdefault(key, _LoginAttemptState())
                state.last_activity = now
                state.failures += 1
                if state.failures >= LOGIN_MAX_FAILURES:
                    state.locked_until = now + self._backoff_seconds(state.strikes)
                    state.strikes += 1
                    state.failures = 0

    def record_success(self, username: str, ip: str) -> None:
        with self._lock:
            for key in self._keys(username, ip):
                self._states.pop(key, None)

    @staticmethod
    def _backoff_seconds(strikes: int) -> float:
        return min(LOGIN_MAX_BACKOFF_SECONDS, LOGIN_BASE_BACKOFF_SECONDS * (2.0**strikes))

    def _cleanup(self, now: float) -> None:
        """Drop idle/expired entries once the tracker grows large."""
        if len(self._states) < LOGIN_MAX_TRACKED_KEYS:
            return
        idle_cutoff: float = now - LOGIN_IDLE_CLEANUP_SECONDS
        for key, state in list(self._states.items()):
            if state.last_activity < idle_cutoff and now >= state.locked_until:
                self._states.pop(key, None)


login_rate_limiter: LoginRateLimiter = LoginRateLimiter()


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
