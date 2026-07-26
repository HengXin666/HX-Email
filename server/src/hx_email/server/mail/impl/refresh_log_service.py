"""Refresh log query functions for email accounts.

Stateless functions for paginated log retrieval, failed log lookup,
invalid-token candidate detection, and aggregate statistics.
All queries are scoped to the calling user via email_accounts.user_id.
"""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect


def now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat()


def insert_refresh_log(
    settings: Settings,
    account_id: int,
    email: str,
    status: str,
    message: str,
    error_detail: str,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> int:
    now = completed_at or now_iso()
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO refresh_logs (
                account_id, email, status, message, error_detail,
                started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account_id, email, status, message, error_detail, started_at, now),
        )
        if status == "success":
            connection.execute(
                "UPDATE email_accounts SET last_refresh_at = ? WHERE id = ?",
                (now, account_id),
            )
        return cursor.lastrowid or 0


_LOG_COLUMNS: str = (
    "rl.id, rl.account_id, rl.email, rl.status, rl.message, rl.error_detail, "
    "rl.started_at, rl.completed_at, rl.created_at"
)
_USER_JOIN: str = "JOIN email_accounts ea ON ea.id = rl.account_id AND ea.user_id = ?"


def get_refresh_logs(
    settings: Settings,
    user_id: int,
    account_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, object]:
    """Get paginated refresh logs for the user, optionally filtered by account_id."""
    account_filter: str = "AND rl.account_id = ?" if account_id is not None else ""
    filter_params: tuple[object, ...] = (account_id,) if account_id is not None else ()
    with connect(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT {_LOG_COLUMNS}
            FROM refresh_logs rl
            {_USER_JOIN}
            WHERE 1 = 1 {account_filter}
            ORDER BY rl.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, *filter_params, limit, offset),
        ).fetchall()
        total_row = connection.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM refresh_logs rl
            {_USER_JOIN}
            WHERE 1 = 1 {account_filter}
            """,
            (user_id, *filter_params),
        ).fetchone()

    total_v: int = total_row["cnt"] if total_row is not None else 0
    return {"logs": [dict(row) for row in rows], "total": total_v}


def get_failed_refresh_logs(
    settings: Settings,
    user_id: int,
    limit: int = 50,
) -> list[dict[str, object]]:
    """Get recent failed refresh logs for the user."""
    with connect(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT {_LOG_COLUMNS}
            FROM refresh_logs rl
            {_USER_JOIN}
            WHERE rl.status = 'failed'
            ORDER BY rl.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_invalid_token_candidates(
    settings: Settings,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    """Find the user's accounts whose recent failed refresh suggests invalid tokens.

    Matches error_detail containing 'invalid_grant' or 'AADSTS'.
    """
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT rl.account_id, ea.primary_address AS email, rl.status,
                   rl.error_detail, rl.created_at, rl.completed_at
            FROM refresh_logs rl
            JOIN email_accounts ea ON ea.id = rl.account_id AND ea.user_id = ?
            WHERE rl.status = 'failed'
              AND (rl.error_detail LIKE '%invalid_grant%'
                   OR rl.error_detail LIKE '%AADSTS%')
              AND rl.id IN (
                  SELECT MAX(id) FROM refresh_logs GROUP BY account_id
              )
            ORDER BY rl.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ).fetchall()
    return {"candidates": [dict(row) for row in rows]}


def get_refresh_stats(settings: Settings, user_id: int) -> dict[str, object]:
    """Aggregate refresh statistics across the user's accounts."""
    with connect(settings) as connection:
        counts_row = connection.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN rl.status = 'success' THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN rl.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                   SUM(CASE WHEN rl.status = 'pending' THEN 1 ELSE 0 END) AS pending
            FROM refresh_logs rl
            {_USER_JOIN}
            """,
            (user_id,),
        ).fetchone()
        last_row = connection.execute(
            f"""
            SELECT rl.completed_at
            FROM refresh_logs rl
            {_USER_JOIN}
            ORDER BY rl.id DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    return {
        "total": counts_row["total"] if counts_row is not None else 0,
        "success": (counts_row["success"] or 0) if counts_row is not None else 0,
        "failed": (counts_row["failed"] or 0) if counts_row is not None else 0,
        "pending": (counts_row["pending"] or 0) if counts_row is not None else 0,
        "last_refresh": last_row["completed_at"] if last_row is not None else "",
    }
