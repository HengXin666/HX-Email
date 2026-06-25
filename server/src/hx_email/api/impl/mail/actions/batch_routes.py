"""Batch operation and notification toggle routes for email accounts."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import (
    BatchDelete,
    BatchGroupUpdate,
    BatchNotificationToggle,
    BatchStatusUpdate,
    BatchTagAction,
    TelegramToggle,
)
from hx_email.config import Settings
from hx_email.server.mail.impl.accounts import (
    batch_delete_accounts,
    batch_tag_action,
    batch_toggle_telegram,
    batch_update_group,
    batch_update_status,
    toggle_telegram_notification,
)


def register_batch_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/email-accounts/batch-update-group")
    def batch_update_group_handler(
        payload: BatchGroupUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        updated = batch_update_group(settings, user.id, payload.account_ids, payload.group_id)
        return {"success": True, "updated_count": updated}

    @router.post("/email-accounts/batch-delete")
    def batch_delete_handler(
        payload: BatchDelete,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        deleted = batch_delete_accounts(settings, user.id, payload.account_ids)
        return {"success": True, "deleted_count": deleted}

    @router.post("/email-accounts/batch-update-status")
    def batch_update_status_handler(
        payload: BatchStatusUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        updated = batch_update_status(settings, user.id, payload.account_ids, payload.status)
        return {"success": True, "updated_count": updated}

    @router.post("/email-accounts/batch-notification-toggle")
    def batch_notification_toggle_handler(
        payload: BatchNotificationToggle,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        updated = batch_toggle_telegram(settings, user.id, payload.account_ids, payload.enabled)
        return {"success": True, "updated_count": updated}

    @router.post("/email-accounts/tags")
    def account_tags_action(
        payload: BatchTagAction,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if payload.action not in ("add", "remove"):
            raise HTTPException(status_code=422, detail='Action must be "add" or "remove"')
        ok = batch_tag_action(
            settings,
            user.id,
            payload.account_ids,
            payload.tag_id,
            payload.action,
        )
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return {"success": True}

    @router.post("/email-accounts/{account_id}/telegram-toggle")
    def telegram_toggle_handler(
        account_id: int,
        payload: TelegramToggle,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if not toggle_telegram_notification(settings, user.id, account_id, payload.enabled):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found"
            )
        return {"success": True}
