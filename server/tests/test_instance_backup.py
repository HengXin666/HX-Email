from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.settings_service import get_setting, update_settings


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    token: str = str(response.json()["access_token"])
    return {"Authorization": f"Bearer {token}"}


def enable_registration(client: TestClient, headers: dict[str, str]) -> None:
    response = client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers=headers,
    )
    assert response.status_code == 200


def test_instance_backup_is_admin_only(tmp_path: Path) -> None:
    settings: Settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin-password",
    )
    migrate(settings)
    client: TestClient = TestClient(create_app(settings))
    admin_headers: dict[str, str] = login(client, "admin", "admin-password")
    enable_registration(client, admin_headers)
    user_response = client.post(
        "/api/v1/auth/register",
        json={"username": "ordinary", "password": "ordinary-password"},
    )
    user_headers: dict[str, str] = {
        "Authorization": f"Bearer {user_response.json()['access_token']}"
    }

    assert client.get("/api/v1/data/export", headers=user_headers).status_code == 403
    assert (
        client.post(
            "/api/v1/data/import",
            json={"version": 1},
            headers=user_headers,
        ).status_code
        == 403
    )
    assert client.get("/api/v1/admin/backup/export", headers=user_headers).status_code == 403
    assert (
        client.post(
            "/api/v1/admin/backup/import",
            content=b"not-a-zip",
            headers={**user_headers, "Content-Type": "application/zip"},
        ).status_code
        == 403
    )
    backup_response = client.get("/api/v1/admin/backup/export", headers=admin_headers)
    assert backup_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(backup_response.content)) as archive:
        assert ".hx_email_secret_key" in archive.namelist()


def test_instance_backup_restores_database_secret_and_static_files(tmp_path: Path) -> None:
    source_data: Path = tmp_path / "source"
    source_settings: Settings = Settings(
        data_dir=source_data,
        admin_username="source-admin",
        admin_password="source-password",
    )
    migrate(source_settings)
    update_settings(source_settings, {"telegram_bot_token": "source-token"})
    static_file: Path = source_data / "static" / "img" / "logo.txt"
    static_file.parent.mkdir(parents=True)
    static_file.write_text("portable-logo", encoding="utf-8")
    source_client: TestClient = TestClient(create_app(source_settings))
    source_headers: dict[str, str] = login(
        source_client,
        "source-admin",
        "source-password",
    )
    backup_response = source_client.get("/api/v1/admin/backup/export", headers=source_headers)

    assert backup_response.status_code == 200
    assert backup_response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(backup_response.content)) as archive:
        names: set[str] = set(archive.namelist())
    assert {"manifest.json", "hx_email.sqlite3", ".hx_email_secret_key"}.issubset(names)
    assert "static/img/logo.txt" in names

    target_data: Path = tmp_path / "target"
    target_settings: Settings = Settings(
        data_dir=target_data,
        admin_username="target-admin",
        admin_password="target-password",
    )
    migrate(target_settings)
    (target_data / "old-marker.txt").write_text("replace-me", encoding="utf-8")
    target_client: TestClient = TestClient(create_app(target_settings))
    target_headers: dict[str, str] = login(target_client, "target-admin", "target-password")
    import_response = target_client.post(
        "/api/v1/admin/backup/import",
        content=backup_response.content,
        headers={**target_headers, "Content-Type": "application/zip"},
    )

    assert import_response.status_code == 200
    assert import_response.json() == {"restored": True, "requires_relogin": True}
    assert not (target_data / "old-marker.txt").exists()
    assert (target_data / "static" / "img" / "logo.txt").read_text(encoding="utf-8") == (
        "portable-logo"
    )
    assert get_setting(target_settings, "telegram_bot_token") == "source-token"
    assert login(target_client, "source-admin", "source-password")
    assert (
        target_client.post(
            "/api/v1/auth/login",
            json={"username": "target-admin", "password": "target-password"},
        ).status_code
        == 401
    )


def test_invalid_instance_backup_keeps_existing_data(tmp_path: Path) -> None:
    settings: Settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin-password",
    )
    migrate(settings)
    marker: Path = tmp_path / "keep-marker.txt"
    marker.write_text("keep-me", encoding="utf-8")
    client: TestClient = TestClient(create_app(settings))
    headers: dict[str, str] = login(client, "admin", "admin-password")
    response = client.post(
        "/api/v1/admin/backup/import",
        content=b"not-a-zip",
        headers={**headers, "Content-Type": "application/zip"},
    )

    assert response.status_code == 422
    assert marker.read_text(encoding="utf-8") == "keep-me"
