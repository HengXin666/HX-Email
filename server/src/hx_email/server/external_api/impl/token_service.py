"""External token-status and patrol services.

Expose the per-group token index (how many accounts, how many valid
tokens) and group-scoped batch refresh to API-key consumers.
"""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.server.mail.impl.patrol.index import get_group_token_index
from hx_email.server.mail.impl.patrol.refresh import (
    UNGROUPED_GROUP_ID,
    refresh_group_accounts_sync,
)
from hx_email.server.mail.verification import MailboxProvider


def get_token_status(settings: Settings, user_id: int) -> dict[str, object]:
    """Return the per-group token index plus the ungrouped bucket."""
    index = get_group_token_index(settings, user_id)
    return {
        "groups": [
            {
                "group_id": group.id,
                "name": group.name,
                "allowed_provider": group.allowed_provider,
                "account_count": group.bucket.account_count,
                "oauth_account_count": group.bucket.oauth_account_count,
                "valid_token_count": group.bucket.valid_token_count,
                "invalid_token_count": group.bucket.invalid_token_count,
            }
            for group in index.groups
        ],
        "ungrouped": {
            "account_count": index.ungrouped.account_count,
            "oauth_account_count": index.ungrouped.oauth_account_count,
            "valid_token_count": index.ungrouped.valid_token_count,
            "invalid_token_count": index.ungrouped.invalid_token_count,
        },
    }


def refresh_group_tokens(
    settings: Settings,
    user_id: int,
    group_id: int,
    mailbox_provider: MailboxProvider,
) -> dict[str, object]:
    """Run a group-scoped token patrol and return per-account results.

    group_id 0 refreshes ungrouped accounts; a positive id refreshes that
    group's accounts. Runs synchronously and returns JSON (no SSE) so
    API-key consumers get a single result payload.
    """
    if group_id < UNGROUPED_GROUP_ID:
        return {
            "error": "group_id must be 0 (ungrouped) or a positive group id",
            "summary": {"total": 0, "success": 0, "failed": 0},
            "results": [],
        }
    return refresh_group_accounts_sync(settings, user_id, group_id)
