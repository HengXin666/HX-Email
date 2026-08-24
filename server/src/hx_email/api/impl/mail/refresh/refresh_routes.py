"""Token refresh route registration for email accounts.

SSE streaming endpoints for refreshing OAuth2 tokens across accounts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from hx_email.api.dependencies import require_user
from hx_email.api.impl.mail.refresh.patrol_routes import register_patrol_routes
from hx_email.api.schemas import RefreshSelectedRequest
from hx_email.config import Settings
from hx_email.server.mail.impl.patrol.refresh import (
    refresh_group_accounts,
    refresh_ungrouped_accounts,
)
from hx_email.server.mail.impl.refresh.single import refresh_single_account
from hx_email.server.mail.impl.refresh_service import (
    refresh_all_accounts,
    refresh_failed_accounts,
    refresh_selected_accounts,
)
from hx_email.server.mail.verification import MailboxProvider


def register_refresh_routes(
    router: APIRouter,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    register_patrol_routes(router, settings)

    @router.post("/email-accounts/{account_id}/refresh")
    def refresh_account(
        account_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        result = refresh_single_account(settings, user.id, account_id, mailbox_provider)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(result.get("message", "Refresh failed")),
            )
        return result

    # POST is the canonical method (triggers refreshes); GET kept for legacy clients
    @router.get("/email-accounts/refresh-all", deprecated=True)
    @router.post("/email-accounts/refresh-all")
    def refresh_all(
        authorization: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        user = require_user(settings, authorization)
        return StreamingResponse(
            refresh_all_accounts(settings, user.id, mailbox_provider),
            media_type="text/event-stream",
        )

    @router.post("/email-accounts/{account_id}/retry-refresh")
    def retry_refresh_account(
        account_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        result = refresh_single_account(settings, user.id, account_id, mailbox_provider)
        return result

    @router.get("/email-accounts/refresh-failed", deprecated=True)
    @router.post("/email-accounts/refresh-failed")
    def refresh_failed(
        authorization: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        user = require_user(settings, authorization)
        return StreamingResponse(
            refresh_failed_accounts(settings, user.id, mailbox_provider),
            media_type="text/event-stream",
        )

    @router.get("/email-accounts/trigger-scheduled-refresh", deprecated=True)
    @router.post("/email-accounts/trigger-scheduled-refresh")
    def trigger_scheduled_refresh(
        authorization: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        user = require_user(settings, authorization)
        return StreamingResponse(
            refresh_all_accounts(settings, user.id, mailbox_provider),
            media_type="text/event-stream",
        )

    @router.post("/email-accounts/refresh/group/{group_id}")
    def refresh_group(
        group_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        """Batch-refresh tokens of all OAuth accounts in one group (SSE)."""
        user = require_user(settings, authorization)
        return StreamingResponse(
            refresh_group_accounts(settings, user.id, group_id, mailbox_provider),
            media_type="text/event-stream",
        )

    @router.post("/email-accounts/refresh/ungrouped")
    def refresh_ungrouped(
        authorization: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        """Batch-refresh tokens of OAuth accounts that belong to no group (SSE)."""
        user = require_user(settings, authorization)
        return StreamingResponse(
            refresh_ungrouped_accounts(settings, user.id, mailbox_provider),
            media_type="text/event-stream",
        )

    @router.post("/email-accounts/refresh/selected")
    def refresh_selected(
        payload: RefreshSelectedRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        user = require_user(settings, authorization)
        if not payload.account_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="account_ids must not be empty",
            )
        return StreamingResponse(
            refresh_selected_accounts(settings, user.id, payload.account_ids, mailbox_provider),
            media_type="text/event-stream",
        )
