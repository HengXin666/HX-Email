"""Email fetch orchestration - IMAP fetch + code extraction + persistence + background loop."""

from __future__ import annotations

import logging
import threading
import time
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

_FETCH_LOCK: threading.Lock = threading.Lock()
_FETCH_RUNNING: bool = False
_FETCH_THREAD: threading.Thread | None = None


# ── single-account fetch ──────────────────────────────────────────────────


def fetch_and_store_for_account(
    settings: Settings,
    user_id: int,
    account_id: int,
    mailbox_provider: MailboxProvider | None = None,
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

    email_rows = list_fetch_usable_emails_for_account(settings, user_id, account_id)

    if not email_rows:
        return {
            "account_id": account_id,
            "email": email_addr,
            "messages_stored": 0,
            "codes_found": 0,
            "error": "No usable emails",
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


def fetch_all_active_accounts(settings: Settings) -> dict[str, Any]:
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
        result = fetch_and_store_for_account(settings, row["user_id"], row["id"])
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


# ── background fetch loop ────────────────────────────────────────────────


def start_background_fetch(settings: Settings, interval: int = 120) -> None:
    """Start a background daemon thread that fetches emails periodically.

    Args:
        settings: application settings
        interval: seconds between fetch cycles (default 120)
    """
    global _FETCH_RUNNING, _FETCH_THREAD

    with _FETCH_LOCK:
        if _FETCH_RUNNING:
            return
        _FETCH_RUNNING = True

    def _loop() -> None:
        logger.info("Background email fetch started (interval=%ds)", interval)
        while _FETCH_RUNNING:
            try:
                summary = fetch_all_active_accounts(settings)
                if summary["messages_stored"] > 0 or summary["codes_found"] > 0:
                    logger.info(
                        "Background fetch: %d new messages, %d codes from %d accounts",
                        summary["messages_stored"],
                        summary["codes_found"],
                        summary["accounts_processed"],
                    )
            except Exception:
                logger.exception("Background email fetch error")

            # Sleep in small chunks so we can shut down promptly
            for _ in range(interval):
                if not _FETCH_RUNNING:
                    break
                time.sleep(1)

    _FETCH_THREAD = threading.Thread(target=_loop, daemon=True, name="email-fetcher")
    _FETCH_THREAD.start()


def stop_background_fetch() -> None:
    """Signal the background fetch thread to stop."""
    global _FETCH_RUNNING
    with _FETCH_LOCK:
        _FETCH_RUNNING = False
