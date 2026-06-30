"""Token refresh domain logic for email accounts."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any, cast

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.impl.oauth_tool import try_refresh_oauth_token
from hx_email.server.mail.verification import MailboxProvider

REFRESH_TIMEOUT: int = 15


def sse_event(event: str, data: object) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat()


def _insert_refresh_log(
    settings: Settings,
    account_id: int,
    email: str,
    status: str,
    message: str,
    error_detail: str,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> int:
    """Insert a refresh_log row and return its id."""
    now = completed_at or _now_iso()
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO refresh_logs (
                account_id, email, status, message, error_detail,
                started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                email,
                status,
                message,
                error_detail,
                started_at,
                now,
            ),
        )
        if status == "success":
            connection.execute(
                "UPDATE email_accounts SET last_refresh_at = ? WHERE id = ?",
                (now, account_id),
            )
        return cursor.lastrowid or 0


def refresh_single_account(
    settings: Settings,
    account_id: int,
    mailbox_provider: MailboxProvider,
) -> dict[str, object]:
    """Refresh the OAuth2 token for a single email account.
    Logs the result to refresh_logs and returns a status dict.
    """
    started_at = _now_iso()
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT ea.id, ea.primary_address, ea.client_id, ea.refresh_token, ea.status,
                   g.proxy_url
            FROM email_accounts ea
            LEFT JOIN groups g ON g.id = ea.group_id
            WHERE ea.id = ?
            """,
            (account_id,),
        ).fetchone()
    if row is None:
        return {"account_id": account_id, "success": False, "message": "Account not found"}
    email: str = row["primary_address"]
    client_id_v: str = row["client_id"] or ""
    refresh_token_val: str = row["refresh_token"] or ""
    proxy_url: str = row["proxy_url"] or ""
    account_status: str = row["status"] or "inactive"
    if account_status != "active":
        _insert_refresh_log(
            settings,
            account_id,
            email,
            "failed",
            "Account is not active",
            "account_inactive",
            started_at=started_at,
        )
        return {
            "account_id": account_id,
            "success": False,
            "email": email,
            "message": "Account is not active",
        }
    if not client_id_v or not refresh_token_val:
        _insert_refresh_log(
            settings,
            account_id,
            email,
            "failed",
            "Missing OAuth credentials (client_id or refresh_token)",
            "missing_credentials",
            started_at=started_at,
        )
        return {
            "account_id": account_id,
            "success": False,
            "email": email,
            "message": "Missing OAuth credentials",
        }
    result = try_refresh_oauth_token(client_id_v, refresh_token_val, proxy_url=proxy_url)
    log_status = "success" if result["success"] else "failed"
    _insert_refresh_log(
        settings,
        account_id,
        email,
        log_status,
        str(result.get("message", "")),
        str(result.get("error_detail", "")),
        started_at=started_at,
    )
    return {
        "account_id": account_id,
        "success": result["success"],
        "email": email,
        "message": result.get("message", ""),
        "error_detail": result.get("error_detail", ""),
    }


def _fetch_active_accounts(
    settings: Settings,
) -> list[dict[str, object]]:
    """Return all active email accounts with OAuth credentials."""
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT ea.id, ea.primary_address, ea.client_id, ea.refresh_token, g.proxy_url
            FROM email_accounts ea
            LEFT JOIN groups g ON g.id = ea.group_id
            WHERE ea.status = 'active' AND ea.refresh_token != ''
            ORDER BY ea.id
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "email": row["primary_address"],
            "client_id": row["client_id"],
            "refresh_token": row["refresh_token"],
            "proxy_url": row["proxy_url"] or "",
        }
        for row in rows
    ]


def _refresh_account_batch(
    settings: Settings,
    accounts: list[dict[str, object]],
    mailbox_provider: MailboxProvider,
) -> Generator[str, None, None]:
    """Yield SSE events while refreshing a batch of accounts."""
    total = len(accounts)
    yield sse_event("start", {"total": total})
    success_count = 0
    fail_count = 0
    for index, account in enumerate(accounts):
        account_id: int = cast(Any, account["id"])
        email: str = cast(Any, account["email"])
        started_at = _now_iso()
        cid: str = str(account.get("client_id", ""))
        rt: str = str(account.get("refresh_token", ""))
        proxy_url: str = str(account.get("proxy_url", ""))
        result = try_refresh_oauth_token(cid, rt, proxy_url=proxy_url)
        log_status = "success" if result["success"] else "failed"
        _insert_refresh_log(
            settings,
            account_id,
            email,
            log_status,
            str(result.get("message", "")),
            str(result.get("error_detail", "")),
            started_at=started_at,
        )
        if result["success"]:
            success_count += 1
        else:
            fail_count += 1
        progress: dict[str, object] = {
            "current": index + 1,
            "total": total,
            "account_id": account_id,
            "email": email,
            "success": result["success"],
            "message": result.get("message", ""),
            "error_detail": result.get("error_detail", ""),
        }
        yield sse_event("progress", progress)
    yield sse_event(
        "complete",
        {"total": total, "success": success_count, "failed": fail_count},
    )


def refresh_all_accounts(
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> Generator[str, None, None]:
    """SSE generator: refresh all active email accounts."""
    accounts = _fetch_active_accounts(settings)
    yield from _refresh_account_batch(settings, accounts, mailbox_provider)


def refresh_selected_accounts(
    settings: Settings,
    account_ids: list[int],
    mailbox_provider: MailboxProvider,
) -> Generator[str, None, None]:
    """SSE generator: refresh only selected account IDs."""
    with connect(settings) as connection:
        placeholders = ",".join("?" for _ in account_ids)
        rows = connection.execute(
            f"""
            SELECT ea.id, ea.primary_address, ea.client_id, ea.refresh_token, g.proxy_url
            FROM email_accounts ea
            LEFT JOIN groups g ON g.id = ea.group_id
            WHERE ea.id IN ({placeholders})
              AND ea.status = 'active'
              AND ea.refresh_token != ''
            ORDER BY ea.id
            """,
            tuple(account_ids),
        ).fetchall()
    accounts: list[dict[str, object]] = [
        {
            "id": row["id"],
            "email": row["primary_address"],
            "client_id": row["client_id"],
            "refresh_token": row["refresh_token"],
            "proxy_url": row["proxy_url"] or "",
        }
        for row in rows
    ]
    yield from _refresh_account_batch(settings, accounts, mailbox_provider)


def refresh_failed_accounts(
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> Generator[str, None, None]:
    """SSE generator: refresh accounts whose last refresh_log is 'failed'."""
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT ea.id, ea.primary_address, ea.client_id, ea.refresh_token, g.proxy_url
            FROM email_accounts ea
            LEFT JOIN groups g ON g.id = ea.group_id
            INNER JOIN (
                SELECT account_id, MAX(id) AS max_id
                FROM refresh_logs
                GROUP BY account_id
            ) latest ON ea.id = latest.account_id
            INNER JOIN refresh_logs rl ON rl.id = latest.max_id
            WHERE ea.status = 'active'
              AND ea.refresh_token != ''
              AND rl.status = 'failed'
            ORDER BY ea.id
            """
        ).fetchall()
    accounts: list[dict[str, object]] = [
        {
            "id": row["id"],
            "email": row["primary_address"],
            "client_id": row["client_id"],
            "refresh_token": row["refresh_token"],
            "proxy_url": row["proxy_url"] or "",
        }
        for row in rows
    ]
    yield from _refresh_account_batch(settings, accounts, mailbox_provider)
