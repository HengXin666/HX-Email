"""Lightweight audit logging: insert and query audit_logs."""

from __future__ import annotations

from typing import Any

from hx_email.config import Settings
from hx_email.database import connect


def log_audit(
    settings: Settings,
    user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    detail: str = "",
    ip_address: str = "",
) -> None:
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO audit_logs (user_id, action, resource_type, resource_id, detail, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, action, resource_type, resource_id, detail, ip_address),
        )


def get_audit_logs(
    settings: Settings,
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    resource_type: str | None = None,
) -> dict[str, object]:
    where_clauses: list[str] = []
    params: list[Any] = []

    if action:
        where_clauses.append("action = ?")
        params.append(action)

    if resource_type:
        where_clauses.append("resource_type = ?")
        params.append(resource_type)

    where_sql: str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with connect(settings) as connection:
        total: int = connection.execute(
            f"SELECT COUNT(*) FROM audit_logs {where_sql}", params
        ).fetchone()[0]

        rows = connection.execute(
            f"""
            SELECT id, user_id, action, resource_type, resource_id,
                   detail, ip_address, created_at
            FROM audit_logs
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

    return {
        "logs": [dict(row) for row in rows],
        "total": total,
    }
