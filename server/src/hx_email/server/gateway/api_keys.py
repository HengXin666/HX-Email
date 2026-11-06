"""Per-user router API keys (docs/messaging-router.md section 8.2).

Plain text is ``hxr_`` + 32 random bytes in base64url and is returned once; only the
SHA-256 hash and the first 8 characters are stored. ``last_used_at`` is written at
most once a minute per key so that read traffic does not become write traffic.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect

KEY_PREFIX: Final[str] = "hxr_"
MAX_ACTIVE_KEYS: Final[int] = 20
TOUCH_INTERVAL_SECONDS: Final[float] = 60.0
LAST_TOUCH: dict[int, float] = {}
TOUCH_LOCK: threading.Lock = threading.Lock()


class KeyLimitError(Exception):
    """The user already holds the maximum number of active keys."""


@dataclass(frozen=True)
class IssuedKey:
    id: int
    name: str
    key: str
    key_prefix: str
    created_at: str


def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


# 路由 API Key 按用户签发且只存哈希; 现有外部 API Key 是全局明文, 不能复用
def issue_key(settings: Settings, user_id: int, name: str) -> IssuedKey:
    plain: str = KEY_PREFIX + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    with connect(settings) as connection:
        active: sqlite3.Row | None = connection.execute(
            "SELECT COUNT(*) AS n FROM router_api_keys WHERE user_id = ? AND revoked_at IS NULL",
            (user_id,),
        ).fetchone()
        if active is not None and int(active["n"]) >= MAX_ACTIVE_KEYS:
            raise KeyLimitError(f"at most {MAX_ACTIVE_KEYS} active keys per user")
        cursor: sqlite3.Cursor = connection.execute(
            "INSERT INTO router_api_keys (user_id, name, key_prefix, key_hash) VALUES (?, ?, ?, ?)",
            (user_id, name.strip() or "default", plain[:8], hash_key(plain)),
        )
        key_id: int = int(cursor.lastrowid or 0)
        row: sqlite3.Row | None = connection.execute(
            "SELECT created_at FROM router_api_keys WHERE id = ?", (key_id,)
        ).fetchone()
        connection.commit()
    created: str = str(row["created_at"]) if row is not None else ""
    return IssuedKey(key_id, name.strip() or "default", plain, plain[:8], created)


def list_keys(settings: Settings, user_id: int) -> list[dict[str, object]]:
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            "SELECT id, name, key_prefix, created_at, last_used_at, revoked_at "
            "FROM router_api_keys WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_key(settings: Settings, user_id: int, key_id: int) -> bool:
    with connect(settings) as connection:
        cursor: sqlite3.Cursor = connection.execute(
            "UPDATE router_api_keys SET revoked_at = datetime('now') "
            "WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (key_id, user_id),
        )
        connection.commit()
    return cursor.rowcount > 0


def verify_key(settings: Settings, plain: str) -> int | None:
    """User id behind an active key, or None."""
    if not plain.startswith(KEY_PREFIX):
        return None
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT id, user_id FROM router_api_keys WHERE key_hash = ? AND revoked_at IS NULL",
            (hash_key(plain),),
        ).fetchone()
        if row is None:
            return None
        key_id: int = int(row["id"])
        now: float = time.monotonic()
        with TOUCH_LOCK:
            stale: bool = (
                now - LAST_TOUCH.get(key_id, -TOUCH_INTERVAL_SECONDS) >= TOUCH_INTERVAL_SECONDS
            )
            if stale:
                LAST_TOUCH[key_id] = now
        if stale:
            connection.execute(
                "UPDATE router_api_keys SET last_used_at = datetime('now') WHERE id = ?", (key_id,)
            )
            connection.commit()
    return int(row["user_id"])
