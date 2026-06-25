"""Settings CRUD and system maintenance routes."""

import platform
import sys as sys_module
from typing import Annotated, Any

from fastapi import APIRouter, Header, status

from hx_email.api.dependencies import require_admin, require_user
from hx_email.api.schemas import SettingsUpdate
from hx_email.config import Settings
from hx_email.server.settings_service import (
    VERSION,
    get_all_settings,
    get_setting,
    update_settings,
)


def register_settings_routes(router: APIRouter, settings: Settings) -> None:
    """Register all settings CRUD and system maintenance endpoints."""

    @router.get("/settings")
    def get_settings(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        """Return all system settings as a flat key-value dict."""
        require_user(settings, authorization)
        return get_all_settings(settings)

    @router.put("/settings")
    def put_settings(
        payload: SettingsUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        """Update settings with any subset of fields."""
        require_user(settings, authorization)
        updates: dict[str, Any] = payload.model_dump()
        update_settings(settings, updates)
        return get_all_settings(settings)

    @router.get("/settings/external-api-key/plaintext")
    def get_external_api_key_plaintext(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        """Return the current external API key in plaintext (admin only)."""
        require_admin(settings, authorization)
        key: str = get_setting(settings, "external_api_key", "")
        return {"external_api_key": key}

    @router.get("/system/version-check")
    def version_check(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Return current version info."""
        require_user(settings, authorization)
        return {
            "version": VERSION,
            "latest_version": VERSION,
            "up_to_date": True,
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

    @router.post("/system/trigger-update", status_code=status.HTTP_202_ACCEPTED)
    def trigger_update(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Trigger Docker update (stub)."""
        require_admin(settings, authorization)
        return {"success": True, "message": "Update triggered (stub)"}

    @router.post("/system/test-watchtower")
    def test_watchtower(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Test Watchtower connectivity (stub)."""
        require_user(settings, authorization)
        return {"success": True, "message": "Watchtower connectivity OK (stub)"}

    @router.post("/system/reload-plugins")
    def reload_plugins(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Reload temp email plugins (stub)."""
        require_user(settings, authorization)
        return {"success": True, "message": "Plugins reloaded (stub)"}
