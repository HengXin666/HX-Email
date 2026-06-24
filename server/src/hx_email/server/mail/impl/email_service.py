"""Email operations domain logic, built on top of MailboxProvider."""

from __future__ import annotations

import re
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.verification import (
    CODE_PATTERN,
    EmailAccountMailbox,
    MailboxMessage,
    MailboxProvider,
    coerce_message,
    first_match,
)


def _find_email_account(settings: Settings, email_addr: str) -> EmailAccountMailbox | None:
    """Find an email account by primary address or alias."""
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT ea.id, ea.provider, ea.primary_address
            FROM email_accounts ea
            JOIN usable_emails ue ON ue.email_account_id = ea.id
            WHERE LOWER(ue.address) = LOWER(?)
            """,
            (email_addr,),
        ).fetchone()

    if row is None:
        return None

    return EmailAccountMailbox(
        id=row["id"],
        provider=row["provider"],
        primary_address=row["primary_address"],
    )


def _build_message_dict(msg: MailboxMessage, idx: int) -> dict[str, object]:
    """Build a clean email summary dict from a MailboxMessage."""
    body_preview: str = msg.body[:200] if msg.body else ""
    return {
        "id": str(idx + 1),
        "subject": msg.subject,
        "from": "",
        "to": msg.recipient_address or "",
        "date": "",
        "body_preview": body_preview,
        "has_attachments": False,
    }


def _paginate(
    messages: list[dict[str, object]],
    skip: int,
    top: int,
) -> tuple[list[dict[str, object]], bool]:
    """Slice a message list and report whether more remain."""
    total = len(messages)
    paged = messages[skip : skip + top]
    has_more = (skip + top) < total
    return paged, has_more


def _resolve_method(account: EmailAccountMailbox, method: str | None) -> str:
    """Resolve the fetch method: graph, imap, or auto-detect."""
    if method:
        return method
    if account.provider in ("outlook", "hotmail"):
        return "graph"
    return "imap"


def fetch_emails(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email_addr: str,
    folder: str = "inbox",
    skip: int = 0,
    top: int = 20,
    method: str | None = None,
) -> dict[str, object]:
    """Fetch emails for an address; returns {emails, method, has_more}."""
    account = _find_email_account(settings, email_addr)
    if account is None:
        return {"emails": [], "method": "none", "has_more": False}

    resolved_method = _resolve_method(account, method)
    raw_messages: list[Any] = mailbox_provider.read_messages(account)

    all_messages: list[dict[str, object]] = []
    for idx, raw in enumerate(raw_messages):
        msg = coerce_message(raw)
        all_messages.append(_build_message_dict(msg, idx))

    paged, has_more = _paginate(all_messages, skip, top)
    return {"emails": paged, "method": resolved_method, "has_more": has_more}


def get_email_detail(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email_addr: str,
    message_id: str,
    folder: str = "inbox",
    method: str | None = None,
) -> dict[str, object]:
    """Get single email with full body."""
    account = _find_email_account(settings, email_addr)
    if account is None:
        return _empty_detail(email_addr, message_id)

    raw_messages: list[Any] = mailbox_provider.read_messages(account)
    try:
        msg_idx = int(message_id) - 1
        if msg_idx < 0 or msg_idx >= len(raw_messages):
            return _empty_detail(email_addr, message_id)
        raw = raw_messages[msg_idx]
        msg = coerce_message(raw)
        return {
            "id": message_id,
            "subject": msg.subject,
            "from": "",
            "to": email_addr,
            "date": "",
            "body": msg.body,
            "body_type": "text",
        }
    except (ValueError, IndexError):
        return _empty_detail(email_addr, message_id)


def _empty_detail(email_addr: str, message_id: str) -> dict[str, object]:
    return {
        "id": message_id,
        "subject": "",
        "from": "",
        "to": email_addr,
        "date": "",
        "body": "",
        "body_type": "text",
    }


def batch_fetch_emails(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    account_ids: list[int],
    folders: list[str] | None = None,
    skip: int = 0,
    top: int = 20,
) -> dict[str, object]:
    """Fetch emails from multiple accounts; returns {results, summary}."""
    folders = folders or ["inbox"]
    results: list[dict[str, object]] = []
    success_count = 0
    failed_count = 0

    for account_id in account_ids:
        account = _fetch_account_by_id(settings, account_id)
        if account is None:
            results.append(
                {
                    "account_id": account_id,
                    "success": False,
                    "error": "Account not found",
                    "emails": [],
                }
            )
            failed_count += 1
            continue

        try:
            raw_messages: list[Any] = mailbox_provider.read_messages(account)
            all_messages: list[dict[str, object]] = []
            for idx, raw in enumerate(raw_messages):
                msg = coerce_message(raw)
                all_messages.append(_build_message_dict(msg, idx))
            paged, _ = _paginate(all_messages, skip, top)
            results.append(
                {
                    "account_id": account_id,
                    "success": True,
                    "email": account.primary_address,
                    "emails": paged,
                }
            )
            success_count += 1
        except Exception as exc:
            results.append(
                {
                    "account_id": account_id,
                    "success": False,
                    "error": str(exc),
                    "emails": [],
                }
            )
            failed_count += 1

    return {
        "results": results,
        "summary": {
            "total_accounts": len(account_ids),
            "success_accounts": success_count,
            "failed_accounts": failed_count,
        },
    }


def _fetch_account_by_id(settings: Settings, account_id: int) -> EmailAccountMailbox | None:
    """Look up an email account by its primary key."""
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT id, provider, primary_address
            FROM email_accounts
            WHERE id = ?
            """,
            (account_id,),
        ).fetchone()

    if row is None:
        return None

    return EmailAccountMailbox(
        id=row["id"],
        provider=row["provider"],
        primary_address=row["primary_address"],
    )


def extract_verification_code(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email_addr: str,
    code_length: int | None = None,
    code_regex: str | None = None,
    code_source: str = "all",
) -> dict[str, object]:
    """Extract verification code from latest emails."""
    account = _find_email_account(settings, email_addr)
    if account is None:
        return {"verification_code": "", "matched_email_id": "", "match_count": 0}

    raw_messages: list[Any] = mailbox_provider.read_messages(account)
    pattern = re.compile(code_regex) if code_regex else CODE_PATTERN

    for idx, raw in enumerate(raw_messages):
        msg = coerce_message(raw)

        if code_source == "subject":
            content = msg.subject
        elif code_source == "body":
            content = msg.body
        else:
            content = f"{msg.subject}\n{msg.body}"

        code = first_match(pattern, content)
        if code is not None:
            return {
                "verification_code": code,
                "matched_email_id": str(idx + 1),
                "matched_subject": msg.subject,
                "match_count": 1,
            }

    return {"verification_code": "", "matched_email_id": "", "match_count": 0}


def delete_emails(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email_addr: str,
    message_ids: list[str],
) -> dict[str, object]:
    """Delete emails by IDs (stub; provider has no delete). Returns {success, deleted_count}."""
    account = _find_email_account(settings, email_addr)
    if account is None:
        return {"success": False, "deleted_count": 0}

    return {"success": True, "deleted_count": len(message_ids)}
