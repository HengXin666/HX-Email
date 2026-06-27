"""Pool admin service: cross-user pool listing and state-machine transitions."""

from __future__ import annotations

import math
import sqlite3
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect

_VALID_ACTIONS: frozenset[str] = frozenset(
    {
        "claim",
        "release",
        "complete",
        "freeze",
        "unfreeze",
        "cooldown",
        "retire",
        "add_to_pool",
        "remove_from_pool",
    }
)

_POOL_STATUSES: frozenset[str] = frozenset(
    {"available", "claimed", "completed", "cooling", "frozen", "retired"}
)

_ACTION_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "claim": ("available", "completed", "cooling"),
    "release": ("claimed",),
    "complete": ("claimed", "completed"),
    "freeze": ("available", "claimed", "completed", "cooling"),
    "unfreeze": ("frozen",),
    "cooldown": ("available", "claimed", "completed"),
    "retire": ("available", "claimed", "completed", "cooling", "frozen"),
}


def list_pool_accounts(settings: Settings, filters: dict[str, Any]) -> dict[str, object]:
    in_pool: str | None = filters.get("in_pool")
    pool_status: str | None = filters.get("pool_status")
    provider: str | None = filters.get("provider")
    group_id: int | None = filters.get("group_id")
    search: str | None = filters.get("search")
    page: int = int(filters.get("page", 1))
    page_size: int = int(filters.get("page_size", 20))

    where_clauses: list[str] = []
    params: list[object] = []

    if in_pool is not None and in_pool in ("true", "false"):
        if in_pool == "true":
            where_clauses.append("mpe.id IS NOT NULL")
        else:
            where_clauses.append("mpe.id IS NULL")

    if pool_status:
        where_clauses.append("mpe.status = ?")
        params.append(pool_status)

    if provider:
        where_clauses.append("ea.provider = ?")
        params.append(provider)

    if group_id is not None:
        where_clauses.append("grp.id = ?")
        params.append(group_id)

    if search:
        where_clauses.append("ue.address LIKE ?")
        params.append(f"%{search}%")

    where_sql: str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_sql: str = f"""
        SELECT COUNT(*)
        FROM usable_emails ue
        LEFT JOIN mail_pool_entries mpe ON mpe.usable_email_id = ue.id
        LEFT JOIN email_accounts ea ON ea.id = ue.email_account_id
        LEFT JOIN groups grp ON grp.id = ue.group_id
        LEFT JOIN users u ON u.id = mpe.user_id
        {where_sql}
    """

    base_sql: str = """
        SELECT
            COALESCE(mpe.id, 0) AS entry_id,
            ue.id AS account_id,
            ue.address AS email,
            COALESCE(ea.provider, '') AS provider,
            COALESCE(mpe.status, '') AS pool_status,
            COALESCE(grp.name, '') AS group_name,
            COALESCE(u.username, '') AS claimed_by,
            '' AS claimed_at,
            COALESCE(ue.status, 'active') AS status
        FROM usable_emails ue
        LEFT JOIN mail_pool_entries mpe ON mpe.usable_email_id = ue.id
        LEFT JOIN email_accounts ea ON ea.id = ue.email_account_id
        LEFT JOIN groups grp ON grp.id = ue.group_id
        LEFT JOIN users u ON u.id = mpe.user_id
    """

    with connect(settings) as connection:
        total_count: int = connection.execute(count_sql, params).fetchone()[0]
        offset: int = (page - 1) * page_size
        rows = connection.execute(
            base_sql + where_sql + " ORDER BY ue.id LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()

    total_pages: int = max(1, math.ceil(total_count / page_size))

    return {
        "accounts": [_serialize_account(row) for row in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        },
    }


def execute_pool_action(
    settings: Settings,
    account_id: int,
    action: str,
    params: dict[str, Any],
) -> dict[str, object]:
    if action not in _VALID_ACTIONS:
        raise ValueError(f"Unknown action: {action}")

    if action == "add_to_pool":
        return _add_to_pool(settings, account_id, params)
    if action == "remove_from_pool":
        return _remove_from_pool(settings, account_id)

    return _transition_pool_status(settings, account_id, action, params)


def _add_to_pool(settings: Settings, account_id: int, params: dict[str, Any]) -> dict[str, object]:
    """Add a usable_email to the mail pool. account_id = usable_email_id."""
    user_id: int = int(params.get("caller_id", 0) or 0)
    with connect(settings) as connection:
        usable = connection.execute(
            "SELECT id, user_id FROM usable_emails WHERE id = ?",
            (account_id,),
        ).fetchone()
        if usable is None:
            raise ValueError(f"Usable email {account_id} not found")

        owner_id: int = user_id or usable["user_id"]
        try:
            connection.execute(
                """
                INSERT INTO mail_pool_entries (user_id, usable_email_id, status)
                VALUES (?, ?, 'available')
                """,
                (owner_id, account_id),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Usable email {account_id} is already in the pool") from None

    return {"success": True, "message": f"Account {account_id} added to pool"}


def _remove_from_pool(settings: Settings, account_id: int) -> dict[str, object]:
    """Remove a mail_pool_entry by its entry id (account_id = mail_pool_entry id)."""
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT id FROM mail_pool_entries WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Pool entry {account_id} not found")
        connection.execute("DELETE FROM mail_pool_entries WHERE id = ?", (account_id,))

    return {"success": True, "message": f"Pool entry {account_id} removed"}


def _transition_pool_status(
    settings: Settings,
    entry_id: int,
    action: str,
    params: dict[str, Any],
) -> dict[str, object]:
    allowed: tuple[str, ...] = _ACTION_TRANSITIONS.get(action, ())
    if not allowed:
        raise ValueError(f"No transition defined for action: {action}")

    target_status: str = action
    if action == "claim":
        target_status = "claimed"
    elif action == "release":
        target_status = "available"
    elif action == "complete":
        target_status = "completed"
    elif action == "freeze":
        target_status = "frozen"
    elif action == "unfreeze":
        target_status = "available"
    elif action == "cooldown":
        target_status = "cooling"
    elif action == "retire":
        target_status = "retired"

    with connect(settings) as connection:
        current = connection.execute(
            """
            SELECT mpe.id, mpe.status, mpe.user_id, mpe.claim_key,
                   mpe.claimed_project_key, mpe.completed_project_key,
                   ue.address, ue.status AS ue_status
            FROM mail_pool_entries mpe
            JOIN usable_emails ue ON ue.id = mpe.usable_email_id
            WHERE mpe.id = ?
            """,
            (entry_id,),
        ).fetchone()

        if current is None:
            raise ValueError(f"Pool entry {entry_id} not found")

        current_status: str = current["status"]
        if current_status not in allowed:
            raise ValueError(
                f"Cannot {action} entry {entry_id}: current status is '{current_status}', "
                f"allowed from: {', '.join(allowed)}"
            )

        updates: dict[str, object] = {"status": target_status}

        if action == "claim":
            updates["claim_key"] = params.get("claim_key", "")
            updates["claimed_project_key"] = params.get("project_key", "")
        elif action == "release":
            updates["claim_key"] = ""
            updates["claimed_project_key"] = ""
        elif action == "complete":
            updates["completed_project_key"] = params.get("project_key", "")

        set_clauses: list[str] = [f"{k} = ?" for k in updates]
        values: list[object] = list(updates.values())
        values.append(entry_id)

        connection.execute(
            f"UPDATE mail_pool_entries SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )

    return {
        "success": True,
        "message": f"Entry {entry_id} transitioned to '{target_status}'",
    }


def _serialize_account(row: sqlite3.Row) -> dict[str, object]:
    return {
        # `id` is kept as usable_email_id for backward-compatible list rendering.
        # State-machine actions must use `entry_id`, because mail_pool_entries.id
        # and usable_emails.id are distinct sequences and can collide accidentally.
        "id": row["account_id"],
        "usable_email_id": row["account_id"],
        "entry_id": row["entry_id"],
        "email": row["email"],
        "provider": row["provider"],
        "pool_status": row["pool_status"],
        "group_name": row["group_name"],
        "claimed_by": row["claimed_by"],
        "claimed_at": row["claimed_at"],
        "status": row["status"],
    }
