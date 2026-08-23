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
from hx_email.server.mail.impl.refresh_service import _stagger_sleep, sse_event
from hx_email.server.mail.verification import MailboxProvider

# Sentinel group id meaning "accounts without a group".
UNGROUPED_GROUP_ID: int = 0


def fetch_accounts(
    settings: Settings,
    user_id: int,
    mode: str,
    group_id: int | None = None,
    account_ids: list[int] | None = None,
) -> list[dict[str, object]]:
    """按目标拉取活跃 OAuth 账号列表 (含分组代理), 供巡检线程处理。

    mode: all / failed / group / ungrouped / selected.
    """
    base_select: str = (
        "SELECT ea.id, ea.primary_address, ea.provider, ea.client_id,"
        " ea.refresh_token, COALESCE(g.proxy_url, '') AS proxy_url"
        " FROM email_accounts ea LEFT JOIN groups g ON g.id = ea.group_id"
    )
    where: list[str] = [
        "ea.status = 'active'",
        "ea.user_id = ?",
        "ea.provider IN ('outlook', 'gmail')",
        "ea.refresh_token != ''",
    ]
    params: list[object] = [user_id]
    if mode == "failed":
        where.append(
            "ea.id IN ("
            " SELECT latest.account_id FROM ("
            "  SELECT account_id, MAX(id) AS max_id FROM refresh_logs GROUP BY account_id"
            " ) latest INNER JOIN refresh_logs rl ON rl.id = latest.max_id"
            " WHERE rl.status = 'failed'"
            ")"
        )
    elif mode == "group":
        where.append("ea.group_id = ?")
        params.append(group_id)
    elif mode == "ungrouped":
        where.append("ea.group_id IS NULL")
    elif mode == "selected":
        if not account_ids:
            return []
        placeholders = ",".join("?" for _ in account_ids)
        where.append(f"ea.id IN ({placeholders})")
        params.extend(account_ids)
    sql: str = f"{base_select} WHERE {' AND '.join(where)} ORDER BY ea.id"
    with connect(settings) as connection:
        rows = connection.execute(sql, params).fetchall()
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


def _group_account_scope(group_id: int) -> tuple[int | None, bool]:
    """Map a group id to the account selection (group id / ungrouped flag)."""
    if group_id == UNGROUPED_GROUP_ID:
        return None, True
    return group_id, False


def _refresh_group_accounts_stream(
    settings: Settings,
    user_id: int,
    group_id: int,
) -> Generator[tuple[str, dict[str, object]], None, None]:
    """Streaming core: yields (event, payload) as work progresses.

    ``start`` is emitted right after the fast account-list query so SSE
    consumers receive response headers immediately; each account refresh
    then yields a ``progress`` payload and the run ends with ``complete``.
    """
    group_filter, ungrouped = _group_account_scope(group_id)
    accounts = _fetch_group_accounts(settings, user_id, group_filter, ungrouped=ungrouped)
    total = len(accounts)
    yield "start", {"total": total}
    success_count = 0
    for index, account in enumerate(accounts):
        if index > 0:
            _stagger_sleep(settings)
        result = _refresh_account(settings, account)
        if bool(result["success"]):
            success_count += 1
        progress: dict[str, object] = {
            "current": index + 1,
            "total": total,
            **result,
        }
        yield "progress", progress
    yield "complete", {"total": total, "success": success_count, "failed": total - success_count}


def refresh_group_accounts_sync(
    settings: Settings,
    user_id: int,
    group_id: int,
) -> dict[str, object]:
    """Refresh all OAuth accounts of a group (0 = ungrouped); returns JSON."""
    results: list[dict[str, object]] = []
    summary: dict[str, int] = {"total": 0, "success": 0, "failed": 0}
    for event, payload in _refresh_group_accounts_stream(settings, user_id, group_id):
        if event == "progress":
            results.append(
                {key: value for key, value in payload.items() if key not in ("current", "total")}
            )
        elif event == "complete":
            summary = cast(dict[str, int], payload)
    return {"summary": summary, "results": results}


def refresh_group_accounts(
    settings: Settings,
    user_id: int,
    group_id: int,
    mailbox_provider: MailboxProvider,
) -> Generator[str, None, None]:
    for event, payload in _refresh_group_accounts_stream(settings, user_id, group_id):
        yield sse_event(event, payload)


def refresh_ungrouped_accounts(
    settings: Settings,
    user_id: int,
    mailbox_provider: MailboxProvider,
) -> Generator[str, None, None]:
    yield from refresh_group_accounts(settings, user_id, UNGROUPED_GROUP_ID, mailbox_provider)
