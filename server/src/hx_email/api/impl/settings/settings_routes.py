"""Settings CRUD and system maintenance routes."""

import json
import platform
import sys as sys_module
import urllib.error
import urllib.request
from typing import Annotated, Any

from fastapi import APIRouter, Header, status

from hx_email.api.dependencies import require_admin, require_user
from hx_email.api.schemas import SettingsUpdate
from hx_email.config import Settings
from hx_email.server.settings_service import (
    PROJECT_REPOSITORY_URL,
    VERSION,
    get_all_settings,
    get_setting,
    update_settings,
)

_GITHUB_RELEASES_API = "https://api.github.com/repos/HengXin666/HX-Email/releases/latest"


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
