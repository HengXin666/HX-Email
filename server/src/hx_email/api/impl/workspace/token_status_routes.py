"""Workspace group token-status route registration.

Exposes the per-group token patrol index (account counts, valid/invalid
token counts) plus the ungrouped bucket, used by the group sidebar.
"""

from typing import Annotated

from fastapi import APIRouter, Header

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.mail.impl.patrol.index import get_group_token_index


def register_group_token_status_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/groups/token-status")
    def get_group_token_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        index = get_group_token_index(settings, user.id)
        return {
            "groups": [
                {
                    "id": group.id,
                    "name": group.name,
                    "color": group.color,
                    "proxy_url": group.proxy_url,
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
