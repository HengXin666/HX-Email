from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.server.self_update.docker import DockerRunner, UpdateOutcome

API_PREFIX = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    response = client.post(
        f"{API_PREFIX}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    token: str = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_release_payload(tag: str = "v9.9.9") -> bytes:
    payload: dict[str, str] = {
        "tag_name": tag,
        "name": f"Release {tag}",
        "body": "更新内容",
        "html_url": f"https://github.com/HengXin666/HX-Email/releases/tag/{tag}",
        "published_at": "2026-08-11T00:00:00Z",
    }
    return json.dumps(payload).encode("utf-8")


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_version_check_reports_available_update(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        with patch(
            "hx_email.api.impl.settings.update_routes.urllib.request.urlopen",
            return_value=FakeResponse(make_release_payload("v9.9.9")),
        ):
            response = client.get(f"{API_PREFIX}/system/version-check", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["has_update"] is True
    assert data["up_to_date"] is False
    assert data["latest_version"] == "v9.9.9"
    assert data["title"] == "Release v9.9.9"
    assert data["html_url"].endswith("/releases/tag/v9.9.9")


def test_update_announcement_graceful_when_github_offline(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        with patch(
            "hx_email.api.impl.settings.update_routes.urllib.request.urlopen",
            side_effect=TimeoutError("timeout"),
        ):
            response = client.get(f"{API_PREFIX}/system/update-announcement", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["has_update"] is False
    assert data["up_to_date"] is True
    assert data["title"] == "无法获取更新公告"


def test_update_status_reports_disabled_when_not_enabled(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        response = client.get(f"{API_PREFIX}/system/update/status", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["available"] is False
    assert data["available_reason"] != ""


def test_update_apply_rejected_when_not_enabled(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        response = client.post(
            f"{API_PREFIX}/system/update/apply",
            json={"version": "9.9.9"},
            headers=headers,
        )

    assert response.status_code == 409
    assert "自动更新未启用" in response.json()["detail"]


def test_update_apply_requires_authentication(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            f"{API_PREFIX}/system/update/apply",
            json={"version": "9.9.9"},
        )

    assert response.status_code == 401


def test_update_apply_runs_background_update(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin",
        update_enabled=True,
        update_image="ghcr.io/hengsixin666/hx-email-server:latest",
    )
    status: dict[str, object] | None = None
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        with (
            patch.object(DockerRunner, "availability_reason", return_value=""),
            patch.object(
                DockerRunner,
                "run_update",
                return_value=UpdateOutcome(
                    success=True, message="更新完成, 新版本已启动", output="pulled"
                ),
            ),
        ):
            apply_response = client.post(
                f"{API_PREFIX}/system/update/apply",
                json={"version": "9.9.9"},
                headers=headers,
            )
            assert apply_response.status_code == 200
            deadline: float = time.monotonic() + 5
            while time.monotonic() < deadline:
                status = client.get(f"{API_PREFIX}/system/update/status", headers=headers).json()
                if not status["running"]:
                    break
                time.sleep(0.05)

    assert status is not None
    assert status["running"] is False
    assert status["success"] is True
    assert status["target_version"] == "9.9.9"
    assert status["last_update"] == {}
