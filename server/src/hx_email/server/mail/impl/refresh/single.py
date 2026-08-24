"""单账号 Token 刷新: 独立轮次 (scope='single'), 供手动单卡刷新与旧端点使用."""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.impl.oauth_tool import try_refresh_provider_oauth_token
from hx_email.server.mail.impl.refresh.rounds import (
    create_refresh_round,
    finish_refresh_round,
)
from hx_email.server.mail.impl.refresh_log_service import (
    insert_refresh_log,
    now_iso,
)
from hx_email.server.mail.verification import MailboxProvider


def refresh_single_account(
    settings: Settings,
    user_id: int,
    account_id: int,
    mailbox_provider: MailboxProvider,
) -> dict[str, object]:
    started_at = now_iso()
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT ea.id, ea.primary_address, ea.provider, ea.client_id,
                   ea.refresh_token, ea.status,
                   g.proxy_url
            FROM email_accounts ea
            LEFT JOIN groups g ON g.id = ea.group_id
            WHERE ea.id = ? AND ea.user_id = ?
            """,
            (account_id, user_id),
        ).fetchone()
    if row is None:
        return {"account_id": account_id, "success": False, "message": "Account not found"}
    email: str = row["primary_address"]
    provider: str = row["provider"] or ""
    client_id_v: str = row["client_id"] or ""
    refresh_token_val: str = row["refresh_token"] or ""
    proxy_url: str = row["proxy_url"] or ""
    account_status: str = row["status"] or "inactive"
    round_id: int = create_refresh_round(settings, user_id, "single")
    total, success, failed = 1, 0, 0
    ok: bool = False
    message: str = "Account is not active"
    error_detail: str = "account_inactive"
    if account_status != "active":
        insert_refresh_log(
            settings,
            account_id,
            email,
            "failed",
            "Account is not active",
            "account_inactive",
            started_at=started_at,
            round_id=round_id,
        )
        failed = 1
    elif provider not in ("outlook", "gmail"):
        total = 0
        ok = True
        message = "Password-based account does not require token refresh"
        error_detail = ""
    elif not client_id_v or not refresh_token_val:
        insert_refresh_log(
            settings,
            account_id,
            email,
            "failed",
            "Missing OAuth credentials (client_id or refresh_token)",
            "missing_credentials",
            started_at=started_at,
            round_id=round_id,
        )
        message = "Missing OAuth credentials"
        error_detail = "missing_credentials"
        failed = 1
    else:
        result = try_refresh_provider_oauth_token(
            settings, provider, client_id_v, refresh_token_val, proxy_url, account_id
        )
        ok = bool(result["success"])
        message = str(result.get("message", ""))
        error_detail = str(result.get("error_detail", ""))
        insert_refresh_log(
            settings,
            account_id,
            email,
            "success" if ok else "failed",
            message,
            error_detail,
            started_at=started_at,
            round_id=round_id,
        )
        success, failed = (1, 0) if ok else (0, 1)
    finish_refresh_round(settings, round_id, total, success, failed)
    return {
        "account_id": account_id,
        "success": ok,
        "email": email,
        "message": message,
        "error_detail": error_detail,
    }
