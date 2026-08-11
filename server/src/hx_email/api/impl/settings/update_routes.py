"""Version check and docker self-update routes."""

import json
import urllib.error
import urllib.request
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from hx_email.api.dependencies import require_admin, require_user
from hx_email.config import Settings
from hx_email.server.self_update import DockerRunner, SelfUpdateService, resolve_config
from hx_email.server.settings_service import PROJECT_REPOSITORY_URL, VERSION

_GITHUB_RELEASES_API: str = "https://api.github.com/repos/HengXin666/HX-Email/releases/latest"
_GITHUB_RELEASES_LIST: str = "https://api.github.com/repos/HengXin666/HX-Email/releases"


class NoPublishedReleasesError(RuntimeError):
    """Raised when the repository exists but has no published release yet."""


class UpdateApplyRequest(BaseModel):
    version: str = ""


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


def _release_payload(data: dict[str, object]) -> dict[str, object]:
    latest_version: str = str(data.get("tag_name") or data.get("name") or VERSION)
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


def _fetch_latest_release() -> dict[str, object]:
    request = urllib.request.Request(
        _GITHUB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "HX-Email update checker",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        # releases/latest 404 可能因为仓库还没有任何 Release, 或只有 pre-release/draft
        # 此时回退到 releases 列表取最新一条; 列表也为空则抛出明确的“暂无发布”错误
        latest = _fetch_newest_release_from_list()
        if latest is not None:
            return latest
        raise NoPublishedReleasesError() from error
    return _release_payload(data)


def _fetch_newest_release_from_list() -> dict[str, object] | None:
    request = urllib.request.Request(
        _GITHUB_RELEASES_LIST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "HX-Email update checker",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        items = json.loads(response.read().decode("utf-8"))
    if not isinstance(items, list) or not items:
        return None
    newest: object = items[0]
    if not isinstance(newest, dict):
        return None
    return _release_payload(newest)


def _update_check_payload() -> dict[str, object]:
    """Fetch the latest release announcement with a graceful offline fallback."""
    try:
        payload = _fetch_latest_release()
        payload["up_to_date"] = not bool(payload["has_update"])
        return payload
    except NoPublishedReleasesError:
        return {
            "success": False,
            "source": "github_release",
            "current_version": VERSION,
            "latest_version": VERSION,
            "has_update": False,
            "up_to_date": True,
            "title": "仓库暂无发布版本",
            "body": "GitHub 仓库尚未发布 Release, 请到发布页面查看或等待新版本发布。",
            "html_url": f"{PROJECT_REPOSITORY_URL}/releases",
            "published_at": "",
            "repository_url": PROJECT_REPOSITORY_URL,
        }
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
            "up_to_date": True,
            "title": "无法获取更新公告",
            "body": str(error),
            "html_url": PROJECT_REPOSITORY_URL,
            "published_at": "",
            "repository_url": PROJECT_REPOSITORY_URL,
        }


def register_update_routes(router: APIRouter, settings: Settings) -> None:
    """Register version-check, announcement and self-update endpoints."""
    config = resolve_config(settings)
    service = SelfUpdateService(config, settings.data_dir, DockerRunner(config))

    @router.get("/system/version-check")
    def version_check(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Return current and latest version info (real GitHub check)."""
        require_user(settings, authorization)
        return _update_check_payload()

    @router.get("/system/update-announcement")
    def update_announcement(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Fetch the latest update announcement from GitHub Releases."""
        require_user(settings, authorization)
        return _update_check_payload()

    @router.get("/system/update/status")
    def update_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Return self-update availability and current run state."""
        require_user(settings, authorization)
        return service.status()

    @router.post("/system/update/apply")
    def apply_update(
        payload: UpdateApplyRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Pull the latest images and recreate containers (admin only)."""
        require_admin(settings, authorization)
        try:
            return service.apply(payload.version)
        except RuntimeError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
