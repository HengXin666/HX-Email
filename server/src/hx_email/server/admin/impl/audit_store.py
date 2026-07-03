"""SQLite adapter for audit logs."""

from __future__ import annotations

from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.admin.impl.audit_models import AuditEvent, AuditQuery


class AuditLogRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings: Settings = settings

    def insert(self, event: AuditEvent) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO audit_logs
                    (user_id, action, resource_type, resource_id, detail, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.user_id,
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    event.detail,
                    event.ip_address,
                ),
            )

    def search(self, query: AuditQuery) -> dict[str, object]:
        where_clauses: list[str] = []
        params: list[object] = []

        if query.action:
            where_clauses.append("action = ?")
            params.append(query.action)
        if query.resource_type:
            where_clauses.append("resource_type = ?")
            params.append(query.resource_type)
        if query.user_id is not None:
            where_clauses.append("user_id = ?")
            params.append(query.user_id)

        where_sql: str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        limit: int = max(1, min(query.limit, 200))
        offset: int = max(0, query.offset)

        with connect(self.settings) as connection:
            count_row: Any = connection.execute(
                f"SELECT COUNT(*) FROM audit_logs {where_sql}", params
            ).fetchone()
            rows: Any = connection.execute(
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

        total: int = int(count_row[0]) if count_row is not None else 0
        return {"logs": [dict(row) for row in rows], "total": total}
