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
                "UPDATE email_accounts"
                " SET last_refresh_at = ?, refresh_failed_at = NULL WHERE id = ?",
                (now, account_id),
            )
        elif status == "failed":
            # 首次从成功/未失败状态转入失败时, 记录该转移时间; 后续连续失败保持原值
            connection.execute(
                "UPDATE email_accounts SET refresh_failed_at = COALESCE(refresh_failed_at, ?)"
                " WHERE id = ?",
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


# 刷新失败错误码分类 (OAuth 错误文本 => 可读分类)。
# 微软 AADSTS 错误码含义参考 Microsoft Entra 文档:
#   令牌失效: 700082/50173/700081 (refresh token 过期/不活跃), invalid_grant
#   应用配置: 700016 (应用不存在), 7000215/7000218/7000222 (client secret 问题), 70011 (scope 无效)
#   账号访问: 50057 (账号被禁用), 50076/50079 (MFA), 65001 (未同意授权), 50034 (用户不存在)
#   密码错误: 50126 (凭据无效)
#   账号锁定/密码过期: 50053 (已锁定), 50055 (密码过期)
#   20260822 风控细分: AADSTS70000 按错误描述拆「服务滥用」(service abuse mode)
#     与「安全验证中断/疑似泄露」(security interrupt / compromised), 同一错误码
#     两种触发, 分布必须分开 (abuse 无法密保取件恢复, compromised 可以)。
MICROSOFT_TOKEN_EXPIRED_CODES: tuple[str, ...] = (
    "invalid_grant",
    "aadsts700082",
    "aadsts50173",
    "aadsts700081",
    "aadsts54005",
)
MICROSOFT_APP_CONFIG_CODES: tuple[str, ...] = (
    "aadsts700016",
    "aadsts7000215",
    "aadsts7000218",
    "aadsts7000222",
    "aadsts70011",
)
MICROSOFT_ACCOUNT_ACCESS_CODES: tuple[str, ...] = (
    "aadsts50057",
    "aadsts50076",
    "aadsts50079",
    "aadsts65001",
    "aadsts50034",
    "aadsts70000",
)
MICROSOFT_PASSWORD_CODES: tuple[str, ...] = ("aadsts50126",)
MICROSOFT_LOCKED_CODES: tuple[str, ...] = (
    "aadsts50053",
    "aadsts50055",
)
# AADSTS70000 内部细分 (按错误描述文本, 20260822 实测两类触发)
ABUSE_HINTS: tuple[str, ...] = (
    "service abuse",
    "abuse mode",
)
COMPROMISED_HINTS: tuple[str, ...] = (
    "compromised",
    "security interrupt",
    "collecting proof",
)
NETWORK_HINTS: tuple[str, ...] = (
    "httpsconnectionpool",
    "connection",
    "timeout",
    "network error",
    "max retries",
    "proxyerror",
)


def classify_refresh_error(provider: str, error_detail: str) -> tuple[str, str]:
    """将刷新失败的错误详情归类为 (category, label)。

    至少覆盖微软五种常见错误: 令牌失效 / 应用配置错误 / 账号访问被拒 /
    密码错误 / 账号锁定, 外加风控细分 (AADSTS70000 服务滥用 vs 安全中断)、
    网络与兜底其他; 谷歌区分令牌失效与网络。
    """
    detail: str = (error_detail or "").lower()
    if any(hint in detail for hint in NETWORK_HINTS):
        return "network", "网络/超时"
    if provider == "gmail":
        if "invalid_grant" in detail or "expired" in detail or "revoked" in detail:
            return "token_expired", "令牌失效/已撤销"
        return "other", "其他错误"
    # Microsoft (outlook)
    if "aadsts70000" in detail:
        if any(hint in detail for hint in ABUSE_HINTS):
            return "account_abuse", "风控-服务滥用"
        if any(hint in detail for hint in COMPROMISED_HINTS):
            return "account_compromised", "风控-安全验证中断"
        return "account_access", "账号/权限被拒"
    if any(code in detail for code in MICROSOFT_TOKEN_EXPIRED_CODES):
        return "token_expired", "令牌失效/过期"
    if any(code in detail for code in MICROSOFT_APP_CONFIG_CODES):
        return "app_config", "应用配置错误"
    if any(code in detail for code in MICROSOFT_PASSWORD_CODES):
        return "password", "密码错误"
    if any(code in detail for code in MICROSOFT_LOCKED_CODES):
        return "account_locked", "账号锁定/密码过期"
    if any(code in detail for code in MICROSOFT_ACCOUNT_ACCESS_CODES):
        return "account_access", "账号/权限被拒"
    return "other", "其他错误"
