"""Browser notification endpoints: new-mail polling and per-email/group mute toggles."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import EnabledToggle
from hx_email.config import Settings
from hx_email.server.workspace.notifications import (
    list_latest_messages,
    poll_notifications,
    set_email_notify,
    set_group_notify,
    set_group_polling,
)


def register_notification_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/overview/latest-messages")
    def latest_messages(
        limit: int = 20,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return {"messages": list_latest_messages(settings, user.id, limit)}

    @router.get("/notifications")
    def list_notifications(
        since_id: int = -1,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """New-mail feed for browser notifications; since_id=-1 initializes the cursor."""
        user = require_user(settings, authorization)
        return poll_notifications(settings, user.id, since_id)

    @router.put("/usable-emails/{usable_email_id}/notify")
    def toggle_email_notify(
        usable_email_id: int,
        payload: EnabledToggle,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if not set_email_notify(settings, user.id, usable_email_id, payload.enabled):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        return {"id": usable_email_id, "notify_enabled": payload.enabled}

    @router.put("/groups/{group_id}/notify")
    def toggle_group_notify(
        group_id: int,
        payload: EnabledToggle,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if not set_group_notify(settings, user.id, group_id, payload.enabled):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        return {"id": group_id, "notify_enabled": payload.enabled}

    @router.put("/groups/{group_id}/polling")
    def toggle_group_polling(
        group_id: int,
        payload: EnabledToggle,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if not set_group_polling(settings, user.id, group_id, payload.enabled):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        return {"id": group_id, "polling_enabled": payload.enabled}
