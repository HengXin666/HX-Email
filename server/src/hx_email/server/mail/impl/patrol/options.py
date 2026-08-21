"""Group provider-channel restriction (allowed_provider) support.

A group can restrict which mail channel (provider) its accounts may use,
e.g. a "Gmail 号" group only accepts gmail accounts. An empty
allowed_provider means any channel is allowed. The restriction is stored on
the groups table and enforced at every account→group assignment point.
"""

from __future__ import annotations

from sqlite3 import Connection

from hx_email.config import Settings
from hx_email.database import connect

KNOWN_PROVIDERS: frozenset[str] = frozenset(
    {
        "gmail",
        "outlook",
        "qq",
        "163",
        "126",
        "aliyun",
        "yahoo",
        "custom",
        "temp_mail",
    }
)


def normalize_allowed_provider(value: str | None) -> str:
    """Normalize an allowed_provider value; '' means unrestricted."""
    provider: str = (value or "").strip().lower()
    return provider


def validate_allowed_provider(value: str | None) -> str:
    """Validate and normalize an allowed_provider value.

    Raises ValueError for unknown provider channels so typos fail loudly
    instead of silently creating an unusable restriction.
    """
    provider: str = normalize_allowed_provider(value)
    if provider and provider not in KNOWN_PROVIDERS:
        raise ValueError(f"Unknown provider channel: {provider}")
    return provider


def set_group_allowed_provider(
    settings: Settings,
    user_id: int,
    group_id: int,
    allowed_provider: str | None,
) -> bool:
    """Persist the channel restriction of a group; returns True when updated."""
    provider: str = validate_allowed_provider(allowed_provider)
    with connect(settings) as connection:
        cursor = connection.execute(
            "UPDATE groups SET allowed_provider = ? WHERE id = ? AND user_id = ?",
            (provider, group_id, user_id),
        )
    return cursor.rowcount > 0


def group_allows_provider(
    settings: Settings,
    user_id: int,
    group_id: int,
    provider: str,
    connection: Connection | None = None,
) -> bool:
    """Whether the group's channel restriction accepts ``provider``."""
    if connection is not None:
        row = connection.execute(
            "SELECT allowed_provider FROM groups WHERE id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
    else:
        with connect(settings) as connection:
            row = connection.execute(
                "SELECT allowed_provider FROM groups WHERE id = ? AND user_id = ?",
                (group_id, user_id),
            ).fetchone()
    if row is None:
        return False
    allowed: str = (row["allowed_provider"] or "").strip().lower()
    return not allowed or allowed == (provider or "").strip().lower()


def assert_group_allows_provider(
    settings: Settings,
    user_id: int,
    group_id: int,
    provider: str,
    connection: Connection | None = None,
) -> None:
    """Raise ValueError when the group forbids ``provider``."""
    if not group_allows_provider(settings, user_id, group_id, provider, connection):
        raise ValueError(f"Group does not allow provider '{provider}' (channel restricted)")
