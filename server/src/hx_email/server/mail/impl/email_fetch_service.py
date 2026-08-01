"""Email fetch orchestration - IMAP fetch + code extraction + persistence + background loop."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from hx_email.config import Settings
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.graph.fallback_provider import FallbackMailProvider
from hx_email.server.mail.imap.message_store import get_latest_message_uid
from hx_email.server.mail.impl.fetch.distribution import store_messages_for_usable_emails
from hx_email.server.mail.impl.fetch.reader import read_refresh_messages
from hx_email.server.mail.impl.fetch.targets import list_fetch_usable_emails_for_account
from hx_email.server.mail.verification import (
    MailboxProvider,
    coerce_message,
)

logger = logging.getLogger(__name__)

# ── single-account fetch ──────────────────────────────────────────────────


def fetch_and_store_for_account(
    settings: Settings,
    user_id: int,
    account_id: int,
    mailbox_provider: MailboxProvider | None = None,
    *,
    polling_only: bool = False,
) -> dict[str, Any]:
    """Fetch emails via IMAP for one account, store messages, extract verification codes.

    Returns {account_id, email, messages_stored, codes_found, error}
    """
    from hx_email.database import connect

    provider: MailboxProvider = mailbox_provider or FallbackMailProvider(settings)

    # Load account info
    with connect(settings) as conn:
        row = conn.execute(
            """
            SELECT id, provider, primary_address
            FROM email_accounts WHERE id = ? AND user_id = ?
            """,
            (account_id, user_id),
        ).fetchone()
        if row is None:
            return {
                "account_id": account_id,
                "email": "",
                "messages_stored": 0,
                "codes_found": 0,
                "error": "Account not found",
            }

        email_addr: str = row["primary_address"]
        account = EmailAccountMailbox(
            id=row["id"],
            provider=row["provider"],
            primary_address=row["primary_address"],
        )

    email_rows = list_fetch_usable_emails_for_account(
        settings,
        user_id,
        account_id,
        polling_only=polling_only,
    )

    if not email_rows:
        return {
            "account_id": account_id,
            "email": email_addr,
            "messages_stored": 0,
            "codes_found": 0,
            "error": "" if polling_only else "No usable emails",
        }

    # Fetch from IMAP
    try:
        latest_uid: str = get_latest_message_uid(settings, account_id)
        raw_messages = read_refresh_messages(provider, account, latest_uid=latest_uid)
    except Exception as exc:
        error_msg = _format_fetch_error(account.provider, str(exc) or type(exc).__name__)
        logger.warning(
            "IMAP fetch failed for account %d (%s): %s",
            account_id,
            email_addr,
            error_msg,
        )
        return {
            "account_id": account_id,
            "email": email_addr,
            "messages_stored": 0,
            "codes_found": 0,
            "error": f"IMAP 连接失败: {error_msg}",
        }

    if not raw_messages:
        _mark_account_refreshed(settings, account_id)
        return {
            "account_id": account_id,
            "email": email_addr,
            "messages_stored": 0,
            "codes_found": 0,
            "error": "",
        }

    # Coerce and deduplicate
    messages: list[MailboxMessage] = [coerce_message(m) for m in raw_messages]

    total_stored, codes_found = store_messages_for_usable_emails(
        settings,
        user_id,
        account_id,
        email_rows,
        messages,
    )

    _mark_account_refreshed(settings, account_id)
    return {
        "account_id": account_id,
        "email": email_addr,
        "messages_stored": total_stored,
        "codes_found": codes_found,
        "error": "",
    }


def _format_fetch_error(provider: str, error_msg: str) -> str:
    lowered: str = error_msg.lower()
    auth_failed: bool = (
        "authenticationfailed" in lowered
        or "authentication failed" in lowered
        or "invalid credentials" in lowered
        or "wrong password/app-password" in lowered
    )
    if provider == "gmail" and auth_failed:
        if "oauth" in lowered or "xoauth2" in lowered:
            return (
                "Gmail Google OAuth 认证失败: Google 拒绝了当前 OAuth 凭证。"
                "请在邮箱账号的凭证页面使用 Google 重新授权。"
                f"原始错误: {error_msg}"
            )
        return (
            "Gmail IMAP 认证失败: Google 拒绝了当前保存的 App Password。"
            "请在 Google Account > Security > 2-Step Verification > App passwords "
            "重新生成 16 位 App Password, 并在邮箱账号中覆盖保存; 不要使用 Gmail 登录密码。"
            "如果看不到 IMAP 开关, 个人 Gmail 通常默认启用 IMAP。"
            f"原始错误: {error_msg}"
        )
    return error_msg


def _mark_account_refreshed(settings: Settings, account_id: int) -> None:
    from hx_email.database import connect

    with connect(settings) as conn:
        conn.execute(
            "UPDATE email_accounts SET last_refresh_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), account_id),
        )


# ── bulk fetch (all active accounts) ─────────────────────────────────────


def fetch_all_active_accounts(
    settings: Settings,
    mailbox_provider: MailboxProvider | None = None,
) -> dict[str, Any]:
    """Fetch emails for all active accounts. Returns summary."""
    from hx_email.database import connect

    with connect(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id FROM email_accounts
            WHERE status = 'active' AND (imap_password != '' OR refresh_token != '')
            """
        ).fetchall()

    results: list[dict[str, Any]] = []
    total_stored = 0
    total_codes = 0
    errors = 0

    for row in rows:
        result = fetch_and_store_for_account(
            settings,
            row["user_id"],
            row["id"],
            mailbox_provider,
            polling_only=True,
        )
        results.append(result)
        total_stored += result.get("messages_stored", 0)
        total_codes += result.get("codes_found", 0)
        if result.get("error"):
            errors += 1

    return {
        "accounts_processed": len(rows),
        "messages_stored": total_stored,
        "codes_found": total_codes,
        "errors": errors,
        "results": results,
    }
