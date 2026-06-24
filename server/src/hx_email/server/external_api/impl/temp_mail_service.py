"""External temp mail service: apply and finish temp email tasks."""

import secrets

from hx_email.config import Settings
from hx_email.server.mail.email_accounts import DuplicateUsableEmailError
from hx_email.server.mail.temp_mail import (
    TempMailProvider,
    create_cf_temp_mailbox,
)

# Simple in-memory task store: {task_token: {status, result, detail}}
_temp_tasks: dict[str, dict[str, str]] = {}


def apply_temp_email(
    settings: Settings,
    temp_mail_providers: dict[str, TempMailProvider],
    caller_id: str,
    task_id: str,
    prefix: str | None = None,
    domain: str | None = None,
) -> dict[str, object]:
    """Apply for a new temp email. Returns email address + task_token.

    Uses the first available temp mail provider (cf).
    Stores task in memory for later finish.
    """
    provider = temp_mail_providers.get("cf")
    if provider is None:
        return {"success": False, "message": "Temp mail provider not configured"}

    # Use a synthetic user_id=1 (admin) for system-level temp email operations.
    # The actual ownership tracking is via caller_id/task_id.
    user_id: int = 1
    requested_address: str | None = None
    if prefix or domain:
        parts: list[str] = []
        if prefix:
            parts.append(prefix)
        if domain:
            parts.append(f"@{domain}")
        requested_address = "".join(parts) if parts else None

    try:
        mailbox = create_cf_temp_mailbox(
            settings,
            user_id,
            provider,
            address=requested_address,
            label=f"ext:{caller_id}:{task_id}",
        )
    except DuplicateUsableEmailError:
        return {"success": False, "message": "Temp email already exists"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}

    task_token: str = secrets.token_urlsafe(24)
    _temp_tasks[task_token] = {
        "status": "active",
        "result": "",
        "detail": "",
        "usable_email_id": str(mailbox.usable_email_id),
        "address": mailbox.address,
    }

    return {
        "success": True,
        "email": mailbox.address,
        "task_token": task_token,
        "usable_email_id": mailbox.usable_email_id,
    }


def finish_temp_email(
    settings: Settings,
    task_token: str,
    result: str | None = None,
    detail: str | None = None,
) -> dict[str, object]:
    """Complete/release a temp email task."""
    if task_token not in _temp_tasks:
        return {"success": False, "message": "Task not found"}
    task = _temp_tasks[task_token]
    task["status"] = "completed"
    task["result"] = result or ""
    task["detail"] = detail or ""
    return {
        "success": True,
        "message": "Task finished",
        "task_token": task_token,
        "status": "completed",
    }
