"""Settings CRUD and system maintenance routes."""

import json
import platform
import secrets
import sys as sys_module
import urllib.error
import urllib.request
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
    PROJECT_REPOSITORY_URL,
    VERSION,
    get_all_settings,
    get_setting,
    set_setting,
    update_settings,
)

_GITHUB_RELEASES_API = "https://api.github.com/repos/HengXin666/HX-Email/releases/latest"


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


def _normalize_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in value.strip().lstrip("vV").split("."):
        number = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(number or "0"))
    return tuple(parts)


def _is_newer_version(latest: str, current: str) -> bool:
    latest_parts = _normalize_version(latest)
    current_parts = _normalize_version(current)
    max_len = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (max_len - len(latest_parts))
    current_parts += (0,) * (max_len - len(current_parts))
    return latest_parts > current_parts


def _fetch_latest_release_announcement() -> dict[str, object]:
    request = urllib.request.Request(
        _GITHUB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "HX-Email update checker",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
    latest_version = str(data.get("tag_name") or data.get("name") or VERSION)
    return {
        "success": True,
        "source": "github_release",
        "current_version": VERSION,
        "latest_version": latest_version,
        "has_update": _is_newer_version(latest_version, VERSION),
        "title": data.get("name") or latest_version,
        "body": data.get("body") or "",
        "html_url": data.get("html_url") or PROJECT_REPOSITORY_URL,
        "published_at": data.get("published_at") or "",
        "repository_url": PROJECT_REPOSITORY_URL,
    }


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

    @router.get("/system/version-check")
    def version_check(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Return current version info."""
        require_user(settings, authorization)
        return {
            "version": VERSION,
            "current_version": VERSION,
            "latest_version": VERSION,
            "has_update": False,
            "up_to_date": True,
            "repository_url": PROJECT_REPOSITORY_URL,
        }

    @router.get("/system/update-announcement")
    def update_announcement(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Fetch latest update announcement from GitHub Releases."""
        require_user(settings, authorization)
        try:
            return _fetch_latest_release_announcement()
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ) as error:
            return {
                "success": False,
                "source": "github_release",
                "current_version": VERSION,
                "latest_version": VERSION,
                "has_update": False,
                "title": "无法获取更新公告",
                "body": str(error),
                "html_url": PROJECT_REPOSITORY_URL,
                "published_at": "",
                "repository_url": PROJECT_REPOSITORY_URL,
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
