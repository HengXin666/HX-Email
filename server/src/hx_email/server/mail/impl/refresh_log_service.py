"""Refresh log query functions for email accounts.

Stateless functions for paginated log retrieval, failed log lookup,
invalid-token candidate detection, and aggregate statistics.
"""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect


def get_refresh_logs(
    settings: Settings,
    account_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, object]:
    """Get paginated refresh logs, optionally filtered by account_id."""
    with connect(settings) as connection:
        if account_id is not None:
            rows = connection.execute(
                """
                SELECT id, account_id, email, status, message, error_detail,
                       started_at, completed_at, created_at
                FROM refresh_logs
                WHERE account_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (account_id, limit, offset),
            ).fetchall()
            total_row = connection.execute(
                "SELECT COUNT(*) AS cnt FROM refresh_logs WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        else:
            rows = connection.execute(
                """
                SELECT id, account_id, email, status, message, error_detail,
                       started_at, completed_at, created_at
                FROM refresh_logs
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            total_row = connection.execute("SELECT COUNT(*) AS cnt FROM refresh_logs").fetchone()

    total_v: int = total_row["cnt"] if total_row is not None else 0
    return {"logs": [dict(row) for row in rows], "total": total_v}


def get_failed_refresh_logs(
    settings: Settings,
    limit: int = 50,
) -> list[dict[str, object]]:
    """Get recent failed refresh logs."""
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, account_id, email, status, message, error_detail,
                   started_at, completed_at, created_at
            FROM refresh_logs
            WHERE status = 'failed'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_invalid_token_candidates(
    settings: Settings,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    """Find accounts whose recent failed refresh suggests invalid tokens.

    Matches error_detail containing 'invalid_grant' or 'AADSTS'.
    """
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT rl.account_id, ea.primary_address AS email, rl.status,
                   rl.error_detail, rl.created_at, rl.completed_at
            FROM refresh_logs rl
            JOIN email_accounts ea ON ea.id = rl.account_id
            WHERE rl.status = 'failed'
              AND (rl.error_detail LIKE '%invalid_grant%'
                   OR rl.error_detail LIKE '%AADSTS%')
              AND rl.id IN (
                  SELECT MAX(id) FROM refresh_logs GROUP BY account_id
              )
            ORDER BY rl.id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return {"candidates": [dict(row) for row in rows]}


def get_refresh_stats(settings: Settings) -> dict[str, object]:
    """Aggregate refresh statistics across all accounts."""
    with connect(settings) as connection:
        total_row = connection.execute("SELECT COUNT(*) AS cnt FROM refresh_logs").fetchone()
        success_row = connection.execute(
            "SELECT COUNT(*) AS cnt FROM refresh_logs WHERE status = 'success'"
        ).fetchone()
        failed_row = connection.execute(
            "SELECT COUNT(*) AS cnt FROM refresh_logs WHERE status = 'failed'"
        ).fetchone()
        pending_row = connection.execute(
            "SELECT COUNT(*) AS cnt FROM refresh_logs WHERE status = 'pending'"
        ).fetchone()
        last_row = connection.execute(
            """
            SELECT completed_at FROM refresh_logs
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()

    return {
        "total": total_row["cnt"] if total_row is not None else 0,
        "success": success_row["cnt"] if success_row is not None else 0,
        "failed": failed_row["cnt"] if failed_row is not None else 0,
        "pending": pending_row["cnt"] if pending_row is not None else 0,
        "last_refresh": last_row["completed_at"] if last_row is not None else "",
    }
