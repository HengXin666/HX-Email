from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import ENCRYPTED_PREFIX
from hx_email.server.settings_service import set_setting
from hx_email.server.sync.config import reload_sync_settings, seed_sync_config_from_env
from hx_email.server.sync.scheduler import sync_configured

API_PREFIX = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    response = client.post(
        f"{API_PREFIX}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    token: str = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_sync_settings_persist_and_encrypt_token(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        response = client.put(
            f"{API_PREFIX}/settings",
            json={
                "sync_url": "http://127.0.0.1:18090",
                "sync_token": "secret-token",
                "sync_interval_seconds": "60",
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["sync_url"] == "http://127.0.0.1:18090"
    assert data["sync_token"] == "secret-token"
    assert data["sync_interval_seconds"] == "60"
    with connect(settings) as connection:
        stored = connection.execute(
            "SELECT value FROM system_settings WHERE key = 'sync_token'"
        ).fetchone()
    assert stored is not None
    assert str(stored[0]).startswith(ENCRYPTED_PREFIX)


def test_sync_settings_require_url_and_token_pair(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        url_only = client.put(
            f"{API_PREFIX}/settings",
            json={"sync_url": "http://master.example.com:8080"},
            headers=headers,
        )
        token_only = client.put(
            f"{API_PREFIX}/settings", json={"sync_token": "token"}, headers=headers
        )

    assert url_only.status_code == 422
    assert token_only.status_code == 422


def test_sync_settings_reject_invalid_url(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        response = client.put(
            f"{API_PREFIX}/settings",
            json={"sync_url": "not-a-url", "sync_token": "token"},
            headers=headers,
        )

    assert response.status_code == 422
    assert "http" in response.json()["detail"]


def test_sync_interval_validation(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        too_large = client.put(
            f"{API_PREFIX}/settings",
            json={"sync_interval_seconds": "999999"},
            headers=headers,
        )
        not_integer = client.put(
            f"{API_PREFIX}/settings",
            json={"sync_interval_seconds": "abc"},
            headers=headers,
        )

    assert too_large.status_code == 422
    assert not_integer.status_code == 422


def test_seed_and_reload_sync_config_from_env(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin",
        sync_url="https://master.example.com",
        sync_token="env-token",
    )
    migrate(settings)
    seed_sync_config_from_env(settings)
    reload_sync_settings(settings)

    assert settings.sync_url == "https://master.example.com"
    assert settings.sync_token == "env-token"
    assert sync_configured(settings)

    set_setting(settings, "sync_url", "")
    reload_sync_settings(settings)
    assert settings.sync_url == ""
    assert not sync_configured(settings)


def test_sync_run_now_requires_admin_and_reports_unconfigured(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        anonymous = client.post(f"{API_PREFIX}/sync/run")
        headers = login_admin(client, settings)
        response = client.post(f"{API_PREFIX}/sync/run", headers=headers)

    assert anonymous.status_code == 401
    assert response.status_code == 200
    assert "sync_url" in response.json()["error"]
