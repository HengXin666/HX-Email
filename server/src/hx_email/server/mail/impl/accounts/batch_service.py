"""Batch operations, export, and export token domain logic for email accounts."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import verify_password

EXPORT_TOKEN_TTL_MINUTES: int = 5


def batch_update_group(
    settings: Settings, user_id: int, account_ids: list[int], group_id: int
) -> int:
    """Update group_id for multiple accounts. Returns count of updated accounts."""
    if not account_ids:
        return 0
    with connect(settings) as connection:
        placeholders = ",".join("?" for _ in account_ids)
        cursor = connection.execute(
            f"""UPDATE email_accounts SET group_id = ?
                WHERE user_id = ? AND id IN ({placeholders})""",
            (group_id, user_id, *account_ids),
        )
    return cursor.rowcount


def batch_delete_accounts(settings: Settings, user_id: int, account_ids: list[int]) -> int:
    """Delete multiple accounts and their usable_emails. Returns deleted count."""
    if not account_ids:
        return 0
    with connect(settings) as connection:
        placeholders = ",".join("?" for _ in account_ids)
        connection.execute(
            f"""DELETE FROM usable_emails
                WHERE user_id = ? AND email_account_id IN ({placeholders})""",
            (user_id, *account_ids),
        )
        cursor = connection.execute(
            f"""DELETE FROM email_accounts
                WHERE user_id = ? AND id IN ({placeholders})""",
            (user_id, *account_ids),
        )
    return cursor.rowcount


def batch_update_status(
    settings: Settings, user_id: int, account_ids: list[int], status: str
) -> int:
    """Update status for multiple accounts. Returns count of updated accounts."""
    if not account_ids:
        return 0
    with connect(settings) as connection:
        placeholders = ",".join("?" for _ in account_ids)
        cursor = connection.execute(
            f"""UPDATE email_accounts SET status = ?
                WHERE user_id = ? AND id IN ({placeholders})""",
            (status, user_id, *account_ids),
        )
        if status == "inactive":
            connection.execute(
                f"""UPDATE usable_emails SET status = 'inactive', active = 0
                    WHERE user_id = ? AND email_account_id IN ({placeholders})""",
                (user_id, *account_ids),
            )
    return cursor.rowcount


def batch_toggle_telegram(
    settings: Settings, user_id: int, account_ids: list[int], enabled: bool
) -> int:
    """Toggle telegram notifications for multiple accounts. Returns updated count."""
    if not account_ids:
        return 0
    value: int = 1 if enabled else 0
    with connect(settings) as connection:
        placeholders = ",".join("?" for _ in account_ids)
        cursor = connection.execute(
            f"""UPDATE email_accounts SET telegram_enabled = ?
                WHERE user_id = ? AND id IN ({placeholders})""",
            (value, user_id, *account_ids),
        )
    return cursor.rowcount


def batch_tag_action(
    settings: Settings,
    user_id: int,
    account_ids: list[int],
    tag_id: int,
    action: str,
) -> bool:
    """Add or remove a tag from multiple accounts' primary usable_emails."""
    if not account_ids:
        return True

    with connect(settings) as connection:
        # Verify tag belongs to user
        tag_row = connection.execute(
            "SELECT id FROM tags WHERE id = ? AND user_id = ?",
            (tag_id, user_id),
        ).fetchone()
        if tag_row is None:
            return False

        placeholders = ",".join("?" for _ in account_ids)
        # Get primary usable_email IDs for these accounts
        rows = connection.execute(
            f"""SELECT ue.id
                FROM usable_emails ue
                WHERE ue.user_id = ? AND ue.kind = 'primary'
                  AND ue.email_account_id IN ({placeholders})""",
            (user_id, *account_ids),
        ).fetchall()

        usable_email_ids: list[int] = [row["id"] for row in rows]
        if not usable_email_ids:
            return True

        if action == "add":
            for ue_id in usable_email_ids:
                connection.execute(
                    """INSERT OR IGNORE INTO usable_email_tags (usable_email_id, tag_id)
                       VALUES (?, ?)""",
                    (ue_id, tag_id),
                )
        elif action == "remove":
            ue_placeholders = ",".join("?" for _ in usable_email_ids)
            connection.execute(
                f"""DELETE FROM usable_email_tags
                    WHERE usable_email_id IN ({ue_placeholders}) AND tag_id = ?""",
                (*usable_email_ids, tag_id),
            )
        else:
            return False

    return True


def _format_export_line(account: dict[str, object]) -> str:
    """Format a single account row as a text export line."""
    provider: str = str(account.get("provider", "") or "")
    address: str = str(account.get("primary_address", "") or "")
    password: str = str(account.get("imap_password", "") or "")
    client_id: str = str(account.get("client_id", "") or "")
    refresh_token: str = str(account.get("refresh_token", "") or "")
    if provider == "outlook" or refresh_token:
        return f"{address}----{password}----{client_id}----{refresh_token}"
    if provider == "custom":
        host: str = str(account.get("imap_host", "") or "")
        port: object = account.get("imap_port") or 993
        return f"{address}----{password}----custom----{host}----{port}"
    return f"{address}----{password}----{provider}"


def export_all_accounts_text(settings: Settings, user_id: int) -> str:
    """Export all active accounts as text."""
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT primary_address, provider, imap_host, imap_port, imap_password,
                   client_id, refresh_token
            FROM email_accounts
            WHERE user_id = ? AND status = 'active'
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()
    return "\n".join(_format_export_line(dict(row)) for row in rows)


def export_selected_accounts_text(settings: Settings, user_id: int, group_ids: list[int]) -> str:
    """Export active accounts from selected groups as text."""
    if not group_ids:
        return ""
    with connect(settings) as connection:
        placeholders = ",".join("?" for _ in group_ids)
        rows = connection.execute(
            f"""
            SELECT primary_address, provider, imap_host, imap_port, imap_password,
                   client_id, refresh_token
            FROM email_accounts
            WHERE user_id = ? AND status = 'active' AND group_id IN ({placeholders})
            ORDER BY id
            """,
            (user_id, *group_ids),
        ).fetchall()
    return "\n".join(_format_export_line(dict(row)) for row in rows)


def verify_export_password(settings: Settings, user_id: int, password: str) -> str | None:
    """Verify the user's password and return an export token if correct."""
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        if not verify_password(password, row["password_hash"]):
            return None

    token: str = uuid.uuid4().hex
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=EXPORT_TOKEN_TTL_MINUTES)
    payload: dict[str, str] = {
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
    }
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO system_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (f"export_token:{token}", json.dumps(payload)),
        )
    return token


def validate_export_token(settings: Settings, token: str) -> bool:
    """Check whether an export token exists and has not expired."""
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT value FROM system_settings WHERE key = ?",
            (f"export_token:{token}",),
        ).fetchone()
        if row is None:
            return False
        try:
            data: dict[str, str] = json.loads(row["value"])
            expires_at = datetime.fromisoformat(data["expires_at"])
            if datetime.now(UTC) > expires_at:
                _cleanup_expired_tokens(connection)
                return False
        except (json.JSONDecodeError, KeyError, ValueError):
            return False
    return True


def _cleanup_expired_tokens(connection: object) -> None:
    """Remove expired export tokens from system_settings."""
    from sqlite3 import Connection

    assert isinstance(connection, Connection)
    now = datetime.now(UTC).isoformat()
    rows = connection.execute(
        "SELECT key, value FROM system_settings WHERE key LIKE 'export_token:%'"
    ).fetchall()
    for row in rows:
        try:
            data: dict[str, str] = json.loads(row["value"])
            if data.get("expires_at", "") < now:
                connection.execute("DELETE FROM system_settings WHERE key = ?", (row["key"],))
        except (json.JSONDecodeError, KeyError):
            pass
