"""External pool service: claim, release, complete, stats."""

import secrets
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect


def claim_random(
    settings: Settings,
    caller_id: str,
    task_id: str,
    provider: str | None = None,
    project_key: str | None = None,
    email_domain: str | None = None,
) -> dict[str, object] | None:
    """Claim a random available email from pool.

    Returns account info + claim_token or None if no available entry.
    """
    project_key = project_key or task_id or "default"
    where_extra: str = ""
    params: list[Any] = []

    if provider:
        where_extra += " AND ea.provider = ?"
        params.append(provider)
    if email_domain:
        where_extra += " AND ue.address LIKE ?"
        params.append(f"%@{email_domain}")

    claim_token: str = secrets.token_urlsafe(24)

    with connect(settings) as connection:
        row = connection.execute(
            f"""
            SELECT mpe.id AS entry_id, ue.id AS usable_email_id,
                   ue.address, ue.status AS ue_status,
                   COALESCE(ea.provider, '') AS provider
            FROM mail_pool_entries mpe
            JOIN usable_emails ue ON ue.id = mpe.usable_email_id
            LEFT JOIN email_accounts ea ON ea.id = ue.email_account_id
            WHERE mpe.status IN ('available', 'completed')
              AND ue.status = 'active'
              AND (mpe.completed_project_key = '' OR mpe.completed_project_key != ?)
              {where_extra}
            ORDER BY RANDOM()
            LIMIT 1
            """,
            [project_key, *params],
        ).fetchone()

        if row is None:
            return None

        connection.execute(
            """
            UPDATE mail_pool_entries
            SET status = 'claimed', claim_key = ?, claimed_project_key = ?
            WHERE id = ?
            """,
            (claim_token, project_key, row["entry_id"]),
        )

    return {
        "account_id": row["usable_email_id"],
        "email": row["address"],
        "provider": row["provider"],
        "status": row["ue_status"],
        "claim_token": claim_token,
    }


def claim_release(
    settings: Settings,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    reason: str | None = None,
) -> dict[str, object]:
    """Release a claimed email back to pool by claim_token."""
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id, status, claim_key
            FROM mail_pool_entries
            WHERE usable_email_id = ? AND claim_key = ? AND status = 'claimed'
            """,
            (account_id, claim_token),
        ).fetchone()
        if row is None:
            return {"success": False, "message": "Claim not found or already released"}

        connection.execute(
            """
            UPDATE mail_pool_entries
            SET status = 'available', claim_key = '', claimed_project_key = ''
            WHERE id = ?
            """,
            (row["id"],),
        )
    return {"success": True, "message": "Released"}


def claim_complete(
    settings: Settings,
    account_id: int,
    claim_token: str,
    caller_id: str,
    task_id: str,
    result: str,
    detail: str | None = None,
) -> dict[str, object]:
    """Mark claim as complete."""
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id, status, claim_key, claimed_project_key
            FROM mail_pool_entries
            WHERE usable_email_id = ? AND claim_key = ? AND status = 'claimed'
            """,
            (account_id, claim_token),
        ).fetchone()
        if row is None:
            return {"success": False, "message": "Claim not found or not in claimed state"}

        project_key: str = str(row["claimed_project_key"] or "")
        connection.execute(
            """
            UPDATE mail_pool_entries
            SET status = 'completed', completed_project_key = ?
            WHERE id = ?
            """,
            (project_key, row["id"]),
        )
    return {"success": True, "message": "Completed"}


def get_pool_stats(settings: Settings) -> dict[str, object]:
    """Return pool statistics: total, available, claimed, completed, cooling."""
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT mpe.status, COUNT(*) AS cnt
            FROM mail_pool_entries mpe
            JOIN usable_emails ue ON ue.id = mpe.usable_email_id
            WHERE ue.status = 'active'
            GROUP BY mpe.status
            """
        ).fetchall()

    stats: dict[str, int] = {
        "total": 0,
        "available": 0,
        "claimed": 0,
        "completed": 0,
        "cooling": 0,
        "frozen": 0,
        "retired": 0,
    }
    for row in rows:
        status_name: str = str(row["status"])
        cnt = int(row["cnt"])
        stats[status_name] = cnt
        stats["total"] += cnt
    return dict(stats)
