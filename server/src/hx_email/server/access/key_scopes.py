"""Read and change the scopes of one router API key.

Scopes live in ``router_api_keys.scopes`` as space separated words. The column is
added by ``migrate_router_schema`` with ``LEGACY_SCOPES`` as its default, so rows that
predate scopes keep every capability they had.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.access.scopes import normalize_scopes


def scopes_column(value: object) -> list[str]:
    """Stored text to the list the API returns."""
    return [word for word in str(value or "").split() if word]


def update_scopes(
    settings: Settings, user_id: int, key_id: int, scopes: Iterable[str]
) -> dict[str, object] | None:
    """Replace the scopes of an active key; None when it is not this user's active key."""
    chosen: tuple[str, ...] = normalize_scopes(scopes)
    with connect(settings) as connection:
        cursor: sqlite3.Cursor = connection.execute(
            "UPDATE router_api_keys SET scopes = ? "
            "WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (" ".join(chosen), key_id, user_id),
        )
        connection.commit()
    if cursor.rowcount == 0:
        return None
    return {"id": key_id, "scopes": list(chosen)}
