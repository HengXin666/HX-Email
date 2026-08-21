"""Group-scoped token refresh (patrol) streams.

Selects the active OAuth accounts of one group (or the ungrouped bucket)
and refreshes their tokens. Two entry points share one core:

- ``refresh_group_accounts`` streams SSE events for the web UI.
- ``refresh_group_accounts_sync`` returns JSON results for API-key callers.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, cast

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.impl.oauth_tool import try_refresh_provider_oauth_token
from hx_email.server.mail.impl.refresh_log_service import (
    insert_refresh_log as _insert_refresh_log,
)
from hx_email.server.mail.impl.refresh_log_service import now_iso as _now_iso
from hx_email.server.mail.impl.refresh_service import sse_event
from hx_email.server.mail.verification import MailboxProvider

# Sentinel group id meaning "accounts without a group".
UNGROUPED_GROUP_ID: int = 0


def _fetch_group_accounts(
    settings: Settings,
    user_id: int,
    group_id: int | None,
    ungrouped: bool = False,
) -> list[dict[str, object]]:
    """Return active OAuth accounts of one group (or ungrouped when set)."""
    if ungrouped:
        where = "ea.group_id IS NULL"
        params: tuple[object, ...] = (user_id,)
    else:
        where = "ea.group_id = ?"
        params = (user_id, group_id)
    with connect(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT ea.id, ea.primary_address, ea.provider, ea.client_id,
                   ea.refresh_token, g.proxy_url
            FROM email_accounts ea
            LEFT JOIN groups g ON g.id = ea.group_id
            WHERE ea.user_id = ? AND {where}
              AND ea.status = 'active'
              AND ea.provider IN ('outlook', 'gmail')
              AND ea.refresh_token != ''
            ORDER BY ea.id
            """,
            params,
        ).fetchall()
    return [
        {
            "id": row["id"],
            "email": row["primary_address"],
            "provider": row["provider"],
            "client_id": row["client_id"],
            "refresh_token": row["refresh_token"],
            "proxy_url": row["proxy_url"] or "",
        }
        for row in rows
    ]


def _refresh_account(settings: Settings, account: dict[str, object]) -> dict[str, object]:
    """Refresh one account and write a refresh log; returns its result dict."""
    account_id: int = cast(Any, account["id"])
    email: str = cast(Any, account["email"])
    started_at: str = _now_iso()
    result = try_refresh_provider_oauth_token(
        settings,
        str(account.get("provider", "")),
        str(account.get("client_id", "")),
        str(account.get("refresh_token", "")),
        proxy_url=str(account.get("proxy_url", "")),
        account_id=account_id,
    )
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
        "email": email,
        "provider": account.get("provider", ""),
        "success": bool(result["success"]),
        "message": result.get("message", ""),
        "error_detail": result.get("error_detail", ""),
    }


def refresh_group_accounts_sync(
    settings: Settings,
    user_id: int,
    group_id: int,
) -> dict[str, object]:
    """Refresh all OAuth accounts of a group (0 = ungrouped); returns JSON."""
    accounts = _fetch_group_accounts(
        settings,
        user_id,
        group_id if group_id > 0 else None,
        ungrouped=group_id == UNGROUPED_GROUP_ID,
    )
    results: list[dict[str, object]] = []
    success_count = 0
    for account in accounts:
        result = _refresh_account(settings, account)
        results.append(result)
        if bool(result["success"]):
            success_count += 1
    total = len(accounts)
    return {
        "summary": {
            "total": total,
            "success": success_count,
            "failed": total - success_count,
        },
        "results": results,
    }


def refresh_group_accounts(
    settings: Settings,
    user_id: int,
    group_id: int,
    mailbox_provider: MailboxProvider,
) -> Generator[str, None, None]:
    payload = refresh_group_accounts_sync(settings, user_id, group_id)
    summary = cast(dict[str, int], payload["summary"])
    results = cast(list[dict[str, object]], payload["results"])
    total: int = summary["total"]
    yield sse_event("start", {"total": total})
    for index, result in enumerate(results):
        progress: dict[str, object] = {
            "current": index + 1,
            "total": total,
            **result,
        }
        yield sse_event("progress", progress)
    yield sse_event("complete", summary)


def refresh_ungrouped_accounts(
    settings: Settings,
    user_id: int,
    mailbox_provider: MailboxProvider,
) -> Generator[str, None, None]:
    yield from refresh_group_accounts(settings, user_id, UNGROUPED_GROUP_ID, mailbox_provider)
