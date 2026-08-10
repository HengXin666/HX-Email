"""Settings CRUD and system maintenance routes."""

import platform
import secrets
import sys as sys_module
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.api.dependencies import require_admin, require_user
from hx_email.api.schemas import SettingsUpdate
from hx_email.config import Settings
from hx_email.server.external_api import get_pool_stats
from hx_email.server.mail.email_accounts import has_active_email_account
from hx_email.server.mail.impl.fetch.scheduler import get_polling_status
from hx_email.server.notifications import get_delivery_status
from hx_email.server.settings_service import (
    VERSION,
    get_all_settings,
    get_setting,
    set_setting,
    update_settings,
)


def _validate_email_sender_account(
    settings: Settings,
    user_id: int,
    updates: dict[str, Any],
) -> None:
    configured_value: object = updates.get(
        "email_notification_account_id",
        get_setting(settings, "email_notification_account_id", ""),
    )
    if configured_value is None or configured_value == "":
        return
    try:
        account_id: int = int(str(configured_value).strip())
    except ValueError:
        return
    if not has_active_email_account(settings, user_id, account_id):
        raise ValueError(
            "email_notification_account_id must reference an active account owned by you"
        )


def register_settings_routes(router: APIRouter, settings: Settings) -> None:
    """Register all settings CRUD and system maintenance endpoints."""

    @router.get("/settings")
    def get_settings(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        """Return all system settings as a flat key-value dict."""
        require_admin(settings, authorization)
        return get_all_settings(settings)

    @router.put("/settings")
    def put_settings(
        payload: SettingsUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        """Update settings with any subset of fields."""
        user = require_admin(settings, authorization)
        updates: dict[str, Any] = payload.model_dump()
        try:
            _validate_email_sender_account(settings, user.id, updates)
            update_settings(settings, updates)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return get_all_settings(settings)

    @router.get("/settings/external-api-key/plaintext")
    def get_external_api_key_plaintext(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        """Return the current external API key in plaintext (admin only)."""
        require_admin(settings, authorization)
        key: str = get_setting(settings, "external_api_key", "")
        return {"external_api_key": key}

    @router.post("/settings/external-api-key/rotate")
    def rotate_external_api_key(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        """Generate a new external API key, invalidating the previous primary key."""
        require_admin(settings, authorization)
        key: str = secrets.token_urlsafe(32)
        set_setting(settings, "external_api_key", key)
        return {"external_api_key": key}

    @router.get("/settings/runtime-status")
    def runtime_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Return observable polling, delivery, and external-pool state."""
        require_user(settings, authorization)
        return {
            "polling": get_polling_status(settings),
            "deliveries": get_delivery_status(settings),
            "pool": {
                "enabled": get_setting(settings, "pool_external_enabled", "false") == "true",
                "api_key_configured": bool(get_setting(settings, "external_api_key", "")),
                **get_pool_stats(settings),
            },
        }

    @router.get("/system/deployment-info")
    def deployment_info(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Return deployment info (python version, platform, etc.)."""
        require_user(settings, authorization)
        return {
            "python_version": sys_module.version,
            "platform": platform.platform(),
            "version": VERSION,
        }
