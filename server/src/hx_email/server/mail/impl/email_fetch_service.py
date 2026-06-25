"""Email fetch orchestration - IMAP fetch + code extraction + persistence + background loop."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from hx_email.config import Settings
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.imap.imap_provider import IMAPMailboxProvider
from hx_email.server.mail.imap.message_store import save_messages
from hx_email.server.mail.verification import (
    CODE_PATTERN,
    LINK_PATTERN,
    VerificationMatch,
    coerce_message,
    first_match,
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
) -> dict[str, Any]:
    """Fetch emails via IMAP for one account, store messages, extract verification codes.

    Returns {account_id, email, messages_stored, codes_found, error}
    """
    from hx_email.database import connect

    provider = IMAPMailboxProvider(settings)

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

        # Find all usable_emails for this account
        email_rows = conn.execute(
            "SELECT id, address FROM usable_emails WHERE email_account_id = ? AND user_id = ?",
            (account_id, user_id),
        ).fetchall()

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
        raw_messages = provider.read_messages(account)
    except Exception as exc:
        error_msg = str(exc) or type(exc).__name__
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
        return {
            "account_id": account_id,
            "email": email_addr,
            "messages_stored": 0,
            "codes_found": 0,
            "error": "邮箱中暂无邮件或 IMAP 连接成功但未找到匹配邮件",
        }

    # Coerce and deduplicate
    messages: list[MailboxMessage] = [coerce_message(m) for m in raw_messages]

    total_stored = 0
    codes_found = 0

    # Separate messages with known recipients vs. broadcast (no recipient)
    addressed: list[MailboxMessage] = []
    broadcast: list[MailboxMessage] = []
    for m in messages:
        if m.recipient_address is not None:
            addressed.append(m)
        else:
            broadcast.append(m)

    # Store broadcast messages only once (for the first/primary email) to avoid
    # duplicating the same message across every alias when IMAP omits the To: header.
    primary_row = email_rows[0] if email_rows else None
    if primary_row and broadcast:
        stored = save_messages(settings, user_id, primary_row["id"], account_id, broadcast)
        total_stored += stored
        for msg in broadcast:
            content = f"{msg.subject}\n{msg.body}"
            code = first_match(CODE_PATTERN, content)
            link = first_match(LINK_PATTERN, content)
            if code or link:
                from hx_email.server.mail.verification import save_history

                match = VerificationMatch(
                    code=code,
                    link=link,
                    recipient_address=msg.recipient_address,
                    certainty="medium",
                    subject=msg.subject,
                )
                save_history(settings, user_id, primary_row["id"], (match,))
                codes_found += 1

    # Store addressed messages per matching usable_email
    for email_row in email_rows:
        ue_id: int = email_row["id"]
        ue_addr: str = email_row["address"]

        relevant = [
            m
            for m in addressed
            if m.recipient_address is not None and m.recipient_address.lower() == ue_addr.lower()
        ]
        if not relevant:
            continue

        stored = save_messages(settings, user_id, ue_id, account_id, relevant)
        total_stored += stored

        for msg in relevant:
            content = f"{msg.subject}\n{msg.body}"
            code = first_match(CODE_PATTERN, content)
            link = first_match(LINK_PATTERN, content)
            if code or link:
                from hx_email.server.mail.verification import save_history

                match = VerificationMatch(
                    code=code,
                    link=link,
                    recipient_address=msg.recipient_address,
                    certainty="high",
                    subject=msg.subject,
                )
                save_history(settings, user_id, ue_id, (match,))
                codes_found += 1

    return {
        "account_id": account_id,
        "email": email_addr,
        "messages_stored": total_stored,
        "codes_found": codes_found,
        "error": "",
    }


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
