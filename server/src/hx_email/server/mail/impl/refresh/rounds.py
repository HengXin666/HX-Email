"""刷新轮次 (refresh round): 一次批量/单账号刷新 = 一轮.

refresh_logs.round_id 关联到 refresh_rounds, 支撑「每次刷新成功率」趋势统计
(按轮次而非按天累计 — 每天刷新次数不固定, 天级成功数无法反映单次刷新的成败)。
"""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect


def now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat()


def create_refresh_round(settings: Settings, user_id: int, scope: str) -> int:
    """新建一次刷新轮次, 返回 round_id (供 refresh_logs.round_id 关联)."""
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO refresh_rounds (user_id, scope, started_at, finished_at)
            VALUES (?, ?, ?, '')
            """,
            (user_id, scope, now_iso()),
        )
        return cursor.lastrowid or 0


def finish_refresh_round(
    settings: Settings,
    round_id: int,
    total: int,
    success: int,
    failed: int,
) -> None:
    """写回该轮刷新尝试总数与成败计数."""
    with connect(settings) as connection:
        connection.execute(
            "UPDATE refresh_rounds SET total = ?, success = ?, failed = ?, finished_at = ?"
            " WHERE id = ?",
            (total, success, failed, now_iso(), round_id),
        )


def get_refresh_round_stats(
    settings: Settings,
    user_id: int,
    provider: str | None,
    cutoff_iso: str,
    limit: int = 30,
) -> list[dict[str, object]]:
    """按刷新轮次聚合最近 N 轮的成功/失败/总数 (可只统计单一服务商).

    每轮 = 一次批量或单账号刷新; 返回值按开始时间升序 (最旧在前), 供
    「每次刷新成功率」趋势图使用; 某轮无该服务商账号时整轮省略。
    """
    provider_filter: str = ""
    provider_params: list[object] = []
    if provider:
        provider_filter = " AND ea.provider = ?"
        provider_params.append(provider)
    with connect(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT rl.round_id, rr.started_at, rr.scope,
                   COUNT(*) AS total,
                   SUM(CASE WHEN rl.status = 'success' THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN rl.status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM refresh_logs rl
            JOIN email_accounts ea ON ea.id = rl.account_id AND ea.user_id = ?
            JOIN refresh_rounds rr ON rr.id = rl.round_id
            WHERE rl.round_id IS NOT NULL
              AND rl.completed_at >= ?
              {provider_filter}
            GROUP BY rl.round_id
            ORDER BY rr.started_at DESC, rl.round_id DESC
            LIMIT ?
            """,
            (user_id, cutoff_iso, *provider_params, limit),
        ).fetchall()
    rounds: list[dict[str, object]] = []
    for row in reversed(rows):
        total: int = int(row["total"])
        success: int = int(row["success"])
        failed: int = int(row["failed"])
        rate: float = round(success / total * 100, 1) if total > 0 else 0.0
        rounds.append(
            {
                "round_id": int(row["round_id"]),
                "started_at": row["started_at"],
                "scope": row["scope"] or "",
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": rate,
            }
        )
    return rounds
