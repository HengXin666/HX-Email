"""External mail wait service: wait_for_message and probe status."""

from __future__ import annotations

import secrets
import time
from typing import Any

from hx_email.config import Settings
from hx_email.server.external_api.impl.mail.helpers import (
    _probes,
    build_summary,
    coerce_messages,
    filter_messages,
    resolve_email,
)
from hx_email.server.mail.impl.email_service import _find_email_account
from hx_email.server.mail.verification import (
    MailboxMessage,
    MailboxProvider,
)


def wait_for_message(
    settings: Settings,
    mailbox_provider: MailboxProvider,
    email: str,
    folder: str = "inbox",
    from_contains: str | None = None,
    subject_contains: str | None = None,
    since_minutes: int | None = None,
    timeout_seconds: int = 30,
    poll_interval: int = 5,
    mode: str = "sync",
    claim_token: str | None = None,
) -> dict[str, object]:
    """Block and wait for new message.

    In sync mode: poll until timeout or new message found.
    In async mode: create a probe entry and return probe_id immediately.
    """
    resolved_email = resolve_email(settings, email, claim_token)

    if mode == "async":
        probe_id: str = secrets.token_urlsafe(16)
        _probes[probe_id] = {
            "status": "pending",
            "result": None,
            "created_at": time.time(),
            "email": resolved_email,
            "timeout_seconds": timeout_seconds,
        }
        return {
            "mode": "async",
            "probe_id": probe_id,
            "status": "pending",
        }

    # Sync mode: poll until timeout
    deadline: float = time.monotonic() + timeout_seconds
    account = _find_email_account(settings, resolved_email)
    if account is None:
        return {"found": False, "message": None}

    start_messages: int = len(mailbox_provider.read_messages(account))

    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        account = _find_email_account(settings, resolved_email)
        if account is None:
            continue
        raw_all: list[Any] = mailbox_provider.read_messages(account)
        if len(raw_all) > start_messages:
            new_msgs: list[MailboxMessage] = coerce_messages(raw_all[start_messages:])
            filtered: list[MailboxMessage] = filter_messages(
                new_msgs, from_contains, subject_contains, since_minutes
            )
            if filtered:
                return {
                    "found": True,
                    "message": build_summary(filtered[0], start_messages),
                    "new_count": len(new_msgs),
                }
            start_messages = len(raw_all)

    return {"found": False, "message": None, "timeout": True}


def get_probe_status(probe_id: str) -> dict[str, object]:
    """Return the current status of an async wait-message probe."""
    if probe_id not in _probes:
        return {"found": False, "status": "unknown"}
    probe = _probes[probe_id]
    result: dict[str, object] = dict(probe)
    raw_created_at: object = probe.get("created_at", 0)
    created_at: float = float(raw_created_at) if isinstance(raw_created_at, int | float) else 0.0
    raw_timeout: object = probe.get("timeout_seconds", 30)
    timeout_sec: int = int(raw_timeout) if isinstance(raw_timeout, int | float) else 30
    if time.time() - created_at > timeout_sec and probe["status"] == "pending":
        probe["status"] = "timeout"
        result["status"] = "timeout"
    return result
