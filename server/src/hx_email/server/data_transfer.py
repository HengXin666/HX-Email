import sqlite3
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect, utc_now_iso
from hx_email.security import decrypt_secret, encrypt_secret


class DataImportConflictError(ValueError):
    pass


class DataImportInvalidError(ValueError): ...


def resolve_ref(ids: dict[int, int], old_id: object, entity: str) -> int:
    try:
        new_id = ids.get(int(str(old_id)))
    except (TypeError, ValueError) as error:
        raise DataImportInvalidError(
            f"Import payload has invalid {entity} id: {old_id!r}"
        ) from error
    if new_id is None:
        raise DataImportInvalidError(f"Import payload references unknown {entity} id: {old_id!r}")
    return new_id


def export_core_data(settings: Settings, user_id: int) -> dict[str, object]:
    with connect(settings) as connection:
        email_accounts = rows(
            connection,
            """
            SELECT id, provider, primary_address, display_name, imap_host, imap_port,
                   username, imap_password, client_id, refresh_token, status,
                   group_id, remark, telegram_enabled, last_refresh_at,
                   created_at, last_fetch_at, refresh_failed_at
            FROM email_accounts
            WHERE user_id = ?
            ORDER BY id
            """,
            user_id,
        )
        usable_emails = rows(
            connection,
            """
            SELECT id, email_account_id, address, label, kind, status, group_id,
                   notify_enabled, created_at
            FROM usable_emails
            WHERE user_id = ?
            ORDER BY id
            """,
            user_id,
        )
        groups = rows(
            connection,
            "SELECT id, name, color, proxy_url, notify_enabled, polling_enabled FROM groups"
            " WHERE user_id = ? ORDER BY id",
            user_id,
        )
        tags = rows(
            connection, "SELECT id, name, color FROM tags WHERE user_id = ? ORDER BY id", user_id
        )
        email_tags = rows(
            connection,
            """
            SELECT usable_email_tags.usable_email_id, usable_email_tags.tag_id
            FROM usable_email_tags
            JOIN usable_emails ON usable_emails.id = usable_email_tags.usable_email_id
            WHERE usable_emails.user_id = ?
            ORDER BY usable_email_tags.usable_email_id, usable_email_tags.tag_id
            """,
            user_id,
        )
        platforms = rows(
            connection, "SELECT id, name FROM platforms WHERE user_id = ? ORDER BY id", user_id
        )
        bindings = rows(
            connection,
            """
            SELECT id, usable_email_id, platform_id, status, notes
            FROM platform_bindings
            WHERE user_id = ?
            ORDER BY id
            """,
            user_id,
        )
    for account in email_accounts:
        account["refresh_token"] = decrypt_secret(settings, str(account.get("refresh_token") or ""))
    return {
        "version": 1,
        "email_accounts": email_accounts,
        "usable_emails": usable_emails,
        "groups": groups,
        "tags": tags,
        "usable_email_tags": email_tags,
        "platforms": platforms,
        "platform_bindings": bindings,
        "deferred_capabilities": deferred_capabilities(),
    }


def import_core_data(
    settings: Settings, user_id: int, payload: dict[str, Any]
) -> dict[str, object]:
    try:
        with connect(settings) as connection:
            group_ids = import_groups(connection, user_id, payload)
            tag_ids = import_tags(connection, user_id, payload)
            account_ids = import_email_accounts(settings, connection, user_id, payload, group_ids)
            email_ids = import_usable_emails(connection, user_id, payload, account_ids, group_ids)
            import_usable_email_tags(connection, payload, email_ids, tag_ids)
            platform_ids = import_platforms(connection, user_id, payload)
            import_platform_bindings(connection, user_id, payload, email_ids, platform_ids)
    except sqlite3.IntegrityError as error:
        raise DataImportConflictError("Imported data conflicts with existing user data") from error
    return export_core_data(settings, user_id)


def rows(connection: sqlite3.Connection, query: str, *params: object) -> list[dict[str, object]]:
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def import_groups(
    connection: sqlite3.Connection, user_id: int, payload: dict[str, Any]
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for group in payload.get("groups", []):
        cursor = connection.execute(
            "INSERT INTO groups (user_id, name, color, proxy_url, notify_enabled, polling_enabled)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                user_id,
                group["name"],
                group.get("color", "#58a6ff"),
                group.get("proxy_url", ""),
                int(group.get("notify_enabled", 1)),
                int(group.get("polling_enabled", 1)),
            ),
        )
        ids[int(group["id"])] = inserted_id(cursor)
    return ids


def import_tags(
    connection: sqlite3.Connection, user_id: int, payload: dict[str, Any]
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for tag in payload.get("tags", []):
        cursor = connection.execute(
            "INSERT INTO tags (user_id, name, color) VALUES (?, ?, ?)",
            (user_id, tag["name"], tag.get("color", "#238636")),
        )
        ids[int(tag["id"])] = inserted_id(cursor)
    return ids


def import_email_accounts(
    settings: Settings,
    connection: sqlite3.Connection,
    user_id: int,
    payload: dict[str, Any],
    group_ids: dict[int, int],
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for account in payload.get("email_accounts", []):
        old_group_id = account.get("group_id")
        cursor = connection.execute(
            "INSERT INTO email_accounts (user_id, provider, primary_address, display_name,"
            " imap_host, imap_port, username, imap_password, client_id, refresh_token, status,"
            " group_id, remark, telegram_enabled, last_refresh_at, created_at, last_fetch_at,"
            " refresh_failed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                account["provider"],
                account["primary_address"],
                account.get("display_name", ""),
                account.get("imap_host", ""),
                account.get("imap_port"),
                account.get("username", ""),
                account.get("imap_password", ""),
                account.get("client_id", ""),
                encrypt_secret(settings, str(account.get("refresh_token", ""))),
                account.get("status", "active"),
                group_ids.get(int(old_group_id)) if old_group_id is not None else None,
                account.get("remark", ""),
                1 if account.get("telegram_enabled") else 0,
                account.get("last_refresh_at"),
                account.get("created_at") or utc_now_iso(),
                account.get("last_fetch_at"),
                account.get("refresh_failed_at"),
            ),
        )
        ids[int(account["id"])] = inserted_id(cursor)
    return ids


def import_usable_emails(
    connection: sqlite3.Connection,
    user_id: int,
    payload: dict[str, Any],
    account_ids: dict[int, int],
    group_ids: dict[int, int],
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for email in payload.get("usable_emails", []):
        old_account_id = email.get("email_account_id")
        old_group_id = email.get("group_id")
        cursor = connection.execute(
            """
            INSERT INTO usable_emails (
                user_id, email_account_id, address, label, kind, status, active, group_id,
                notify_enabled, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                account_ids.get(int(old_account_id)) if old_account_id is not None else None,
                email["address"],
                email.get("label", ""),
                email.get("kind", "custom"),
                email.get("status", "active"),
                1 if email.get("status", "active") == "active" else 0,
                group_ids.get(int(old_group_id)) if old_group_id is not None else None,
                int(email.get("notify_enabled", 1)),
                email.get("created_at") or utc_now_iso(),
            ),
        )
        ids[int(email["id"])] = inserted_id(cursor)
    return ids


def import_usable_email_tags(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    email_ids: dict[int, int],
    tag_ids: dict[int, int],
) -> None:
    for link in payload.get("usable_email_tags", []):
        connection.execute(
            "INSERT INTO usable_email_tags (usable_email_id, tag_id) VALUES (?, ?)",
            (
                resolve_ref(email_ids, link.get("usable_email_id"), "usable_email"),
                resolve_ref(tag_ids, link.get("tag_id"), "tag"),
            ),
        )


def import_platforms(
    connection: sqlite3.Connection, user_id: int, payload: dict[str, Any]
) -> dict[int, int]:
    ids: dict[int, int] = {}
    for platform in payload.get("platforms", []):
        cursor = connection.execute(
            "INSERT INTO platforms (user_id, name) VALUES (?, ?)",
            (user_id, platform["name"]),
        )
        ids[int(platform["id"])] = inserted_id(cursor)
    return ids


def import_platform_bindings(
    connection: sqlite3.Connection,
    user_id: int,
    payload: dict[str, Any],
    email_ids: dict[int, int],
    platform_ids: dict[int, int],
) -> None:
    for binding in payload.get("platform_bindings", []):
        connection.execute(
            """
            INSERT INTO platform_bindings (user_id, usable_email_id, platform_id, status, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                resolve_ref(email_ids, binding.get("usable_email_id"), "usable_email"),
                resolve_ref(platform_ids, binding.get("platform_id"), "platform"),
                binding.get("status", "active"),
                binding.get("notes", ""),
            ),
        )


def inserted_id(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite did not return an inserted row id")
    return cursor.lastrowid


def deferred_capabilities() -> list[str]:
    return [
        "browser_extension",
        "full_public_api",
        "notifications",
        "one_click_update",
        "ai_enhancements",
        "plugin_temp_mail_providers",
    ]
